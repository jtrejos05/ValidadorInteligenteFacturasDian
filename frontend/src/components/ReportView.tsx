import type { Finding, Report } from "../api";
import { DECISION_LABEL, money, usd } from "../format";

const SEVERITY_LABEL = { error: "Error", warning: "Alerta", info: "Info" } as const;
const RISK_LABEL: Record<string, string> = { low: "Bajo", medium: "Medio", high: "Alto" };

function FindingRow({ f }: { f: Finding }) {
  return (
    <tr>
      <td>
        <span className={`pill sev-${f.severity}`}>{SEVERITY_LABEL[f.severity]}</span>
      </td>
      <td>
        <span className={`pill src-${f.source}`} title={f.source === "ai" ? "Juicio del modelo" : "Regla determinista"}>
          {f.source === "ai" ? "IA" : "Regla"}
        </span>
      </td>
      <td>
        <code>{f.code}</code>
        <div className="finding-msg">{f.message}</div>
      </td>
      <td className="mono small">
        {f.expected && <div>esperado: {f.expected}</div>}
        {f.actual && <div>recibido: {f.actual}</div>}
        {f.confidence !== null && <div>confianza: {Math.round(f.confidence * 100)}%</div>}
      </td>
    </tr>
  );
}

export function ReportView({ report }: { report: Report }) {
  const inv = report.invoice;
  const cost = report.llm_calls.reduce((s, c) => s + c.cost_usd, 0);
  const tokens = report.llm_calls.reduce((s, c) => s + c.input_tokens + c.output_tokens, 0);

  return (
    <div className="report">
      <div className={`decision decision-${report.decision}`}>
        <div>
          <div className="decision-label">{DECISION_LABEL[report.decision]}</div>
          <div className="decision-reason">{report.decision_reason}</div>
        </div>
        {report.explanation && (
          <div className="risk">
            Riesgo de pago: <strong>{RISK_LABEL[report.explanation.risk_level] ?? report.explanation.risk_level}</strong>
          </div>
        )}
      </div>

      {report.explanation && (
        <section className="card">
          <h3>Explicación</h3>
          <p>{report.explanation.summary}</p>
          {report.explanation.actions.length > 0 && (
            <ul className="actions">
              {report.explanation.actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="card">
        <h3>Factura</h3>
        <dl className="facts">
          <dt>Número</dt>
          <dd>{inv.number ?? "—"}</dd>
          <dt>Emisor</dt>
          <dd>
            {inv.supplier.name ?? "—"} · NIT {inv.supplier.nit ?? "—"}
            {inv.supplier.check_digit ? `-${inv.supplier.check_digit}` : ""}
          </dd>
          <dt>Adquiriente</dt>
          <dd>
            {inv.customer.name ?? "—"} · {inv.customer.nit ?? "—"}
          </dd>
          <dt>Fecha</dt>
          <dd>{inv.issue_date ?? "—"}</dd>
          <dt>Subtotal</dt>
          <dd>{money(inv.line_extension_amount)}</dd>
          <dt>Total a pagar</dt>
          <dd>
            <strong>{money(inv.payable_amount)}</strong>
          </dd>
          <dt>CUFE</dt>
          <dd className="mono small break">{inv.cufe ?? "—"}</dd>
        </dl>
        {inv.lines.length > 0 && (
          <table className="lines">
            <thead>
              <tr>
                <th>#</th>
                <th>Descripción</th>
                <th className="num">Cant.</th>
                <th className="num">Valor</th>
              </tr>
            </thead>
            <tbody>
              {inv.lines.map((l) => (
                <tr key={l.id}>
                  <td>{l.id}</td>
                  <td>{l.description}</td>
                  <td className="num">{Number(l.quantity)}</td>
                  <td className="num">{money(l.line_extension_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>Hallazgos ({report.findings.length})</h3>
        {report.findings.length === 0 ? (
          <p className="muted">Ninguno. La factura superó todas las validaciones.</p>
        ) : (
          <table className="findings">
            <tbody>
              {report.findings.map((f, i) => (
                <FindingRow key={`${f.code}-${i}`} f={f} />
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>Traza</h3>
        <p className="muted small">
          {report.duration_ms} ms en total · {report.llm_calls.length} llamada(s) al modelo · {tokens} tokens ·{" "}
          {usd(cost)}
        </p>
        {report.llm_calls.length > 0 && (
          <table className="trace">
            <thead>
              <tr>
                <th>Propósito</th>
                <th>Modelo</th>
                <th className="num">Tokens in/out</th>
                <th className="num">Latencia</th>
                <th className="num">Costo</th>
              </tr>
            </thead>
            <tbody>
              {report.llm_calls.map((c, i) => (
                <tr key={i}>
                  <td>{c.purpose}</td>
                  <td className="mono small">{c.model}</td>
                  <td className="num">
                    {c.input_tokens}/{c.output_tokens}
                  </td>
                  <td className="num">{c.latency_ms} ms</td>
                  <td className="num">{usd(c.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
