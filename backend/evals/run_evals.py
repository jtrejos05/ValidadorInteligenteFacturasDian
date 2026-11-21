"""Eval harness.

    uv run python -m evals.run_evals            # offline, mock LLM (runs in CI)
    uv run python -m evals.run_evals --live     # real Claude calls (needs ANTHROPIC_API_KEY)

Metrics
- Rule engine: per-code precision / recall against the sown defects.
- AI review: recall on the semantic cases, and false positives on the cases where no
  AI finding is expected (an over-eager model sends too much work to humans).
- End-to-end decision accuracy, cost and latency per invoice.

Exits non-zero when a quality gate fails, so a prompt or rule change that makes
things worse breaks the build.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from app.ai.llm import AnthropicLLM, MockLLM
from app.models import FindingSource
from app.pipeline import validate
from app.samples import load_samples
from app.synthetic import build_invoice_xml
from evals.cases import CASES, EVAL_TODAY

GATES = {
    "rule_recall": 1.0,  # deterministic rules must catch every sown defect
    "rule_precision": 1.0,
    "decision_accuracy": 0.9,
    "ai_recall": 0.66,
    "ai_false_positive_rate": 0.1,
}


def _pr(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return precision, recall


def run(live: bool) -> dict:
    llm = AnthropicLLM() if live else MockLLM()
    per_code = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    ai = {"tp": 0, "fn": 0, "fp_cases": 0, "negative_cases": 0}
    rows, correct, cost, latency = [], 0, 0.0, 0

    items = [
        (
            c.name,
            build_invoice_xml(c.spec).encode(),
            None,
            c.rule_codes,
            c.ai_codes,
            c.expected_decision,
        )
        for c in CASES
    ]
    for name, s in load_samples().items():
        if s.pdf is not None:
            ai_expected = (
                {"PDF_XML_MISMATCH"} if s.expected_decision == "needs_review" and s.xml else set()
            )
            items.append((name, s.xml, s.pdf, set(), ai_expected, s.expected_decision))

    for name, xml, pdf, rule_expected, ai_expected, expected_decision in items:
        started = time.perf_counter()
        report = validate(
            xml=xml,
            attachment=pdf,
            attachment_type="application/pdf" if pdf else None,
            llm=llm,
            today=EVAL_TODAY,
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        latency += elapsed
        cost += sum(c.cost_usd for c in report.llm_calls)

        if xml is not None and pdf is None:
            got_rules = {f.code for f in report.findings if f.source == FindingSource.RULE}
            for code in got_rules | rule_expected:
                key = (
                    "tp"
                    if code in got_rules and code in rule_expected
                    else ("fp" if code in got_rules else "fn")
                )
                per_code[code][key] += 1

        got_ai = {
            f.code for f in report.findings if f.source == FindingSource.AI and f.severity != "info"
        }
        if ai_expected:
            ai["tp"] += len(ai_expected & got_ai)
            ai["fn"] += len(ai_expected - got_ai)
        else:
            ai["negative_cases"] += 1
            ai["fp_cases"] += bool(got_ai - {"XML_MISSING"})

        ok = report.decision.value == expected_decision
        correct += ok
        rows.append(
            {
                "case": name,
                "expected": expected_decision,
                "got": report.decision.value,
                "ok": ok,
                "ai_findings": sorted(got_ai),
                "ms": elapsed,
            }
        )

    tp = sum(v["tp"] for v in per_code.values())
    fp = sum(v["fp"] for v in per_code.values())
    fn = sum(v["fn"] for v in per_code.values())
    rule_p, rule_r = _pr(tp, fp, fn)
    _, ai_r = _pr(ai["tp"], 0, ai["fn"])
    n = len(items)
    return {
        "provider": llm.name,
        "model": llm.model,
        "cases": n,
        "metrics": {
            "rule_precision": round(rule_p, 3),
            "rule_recall": round(rule_r, 3),
            "ai_recall": round(ai_r, 3),
            "ai_false_positive_rate": round(ai["fp_cases"] / ai["negative_cases"], 3)
            if ai["negative_cases"]
            else 0.0,
            "decision_accuracy": round(correct / n, 3),
            "cost_usd_total": round(cost, 4),
            "cost_usd_per_invoice": round(cost / n, 5),
            "avg_latency_ms": round(latency / n),
        },
        "per_code": {k: dict(v) for k, v in sorted(per_code.items())},
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="call Claude instead of the mock")
    parser.add_argument("--out", default="evals/results/latest.json")
    args = parser.parse_args()

    result = run(args.live)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nProvider: {result['provider']} ({result['model']}) - {result['cases']} cases\n")
    print(f"{'case':32} {'expected':13} {'got':13} ai_findings")
    for r in result["rows"]:
        mark = " " if r["ok"] else "X"
        print(
            f"{mark} {r['case']:30} {r['expected']:13} {r['got']:13} {','.join(r['ai_findings'])}"
        )
    print()
    failed = []
    for name, value in result["metrics"].items():
        gate = GATES.get(name)
        status = ""
        if gate is not None:
            passed = value <= gate if name == "ai_false_positive_rate" else value >= gate
            status = "PASS" if passed else "FAIL"
            if not passed:
                failed.append(name)
        print(f"  {name:26} {value!s:>10}  {status}")
    print(f"\nResults written to {out}")
    if failed:
        print(f"Quality gates failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
