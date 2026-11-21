"""Rule engine primitives.

Every rule is a pure function `(RuleContext) -> list[Finding]`. Rules are
deterministic, fast, and unit-tested; they are the source of truth for anything
that can be computed (hashes, check digits, arithmetic, dates).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.models import Finding, Invoice, Severity

Rule = Callable[["RuleContext"], list[Finding]]
_REGISTRY: list[tuple[str, Rule]] = []


@dataclass
class RuleContext:
    invoice: Invoice
    today: date
    resolutions: dict[str, dict] = field(default_factory=dict)
    tolerance: Decimal = Decimal("1.0")


def rule(name: str) -> Callable[[Rule], Rule]:
    def decorator(fn: Rule) -> Rule:
        _REGISTRY.append((name, fn))
        return fn

    return decorator


def registered_rules() -> list[tuple[str, Rule]]:
    return list(_REGISTRY)


def finding(code: str, severity: Severity, message: str, **kwargs) -> Finding:
    return Finding(code=code, severity=severity, message=message, **kwargs)


@lru_cache
def load_resolutions(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def money(value: Decimal | None) -> str:
    """DIAN amount format: two decimals, dot separator, no thousands separator."""
    return f"{(value or Decimal('0')):.2f}"
