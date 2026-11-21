import { useEffect, useState } from "react";
import { api, type Metrics, type Report } from "../api";
import { DECISION_LABEL, dateTime, money, usd } from "../format";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  );
}

export function MetricsPage({ refreshKey }: { refreshKey: number }) {
  const [m, setM] = useState<Metrics | null>(null);
  const [history, setHistory] = useState<Report[]>([]);

  useEffect(() => {
    api.metrics().then(setM).catch(() => setM(null));
    api.reports().then(setHistory).catch(() => setHistory([]));
  }, [refreshKey]);

  if (!m) return <div className="empty">Cargando métricas…</div>;
  const bc = m.business_case;

  return (
    <div className="metrics">
      <div className="stats">
        <Stat label="Facturas procesadas" value={String(m.invoices)} />
        <Stat
          label="Resueltas sin intervención"
          value={`${Math.round(m.auto_resolution_rate * 100)}%`}
          hint={`${m.by_decision.approved} aprobadas · ${m.by_decision.rejected} rechazadas`}
        />
        <Stat label="Pendientes de revisión" value={String(m.pending_reviews)} />
        <Stat label="Costo IA por factura" value={usd(m.llm.cost_per_invoice_usd)} hint={`${m.llm.calls} llamadas · ${m.llm.errors} errores`} />
        <Stat label="Tiempo promedio" value={`${m.avg_duration_ms} ms`} hint={`latencia modelo ${m.llm.avg_latency_ms} ms`} />
        <Stat
          label="Horas de analista ahorradas"
          value={bc.estimated_hours_saved.toFixed(1)}
          hint={`≈ ${money(bc.estimated_cop_saved)} (supuesto: ${bc.assumption_manual_minutes_per_invoice} min/factura, ${money(bc.assumption_analyst_cost_cop_per_hour)}/h)`}
        />
      </div>

      <div className="grid">
        <section className="card">
          <h3>Hallazgos más frecuentes</h3>
          {m.top_findings.length === 0 ? (
            <p className="muted">Aún no hay datos.</p>
          ) : (
            <table>
              <tbody>
                {m.top_findings.map(([code, n]) => (
                  <tr key={code}>
                    <td>
                      <code>{code}</code>
                    </td>
                    <td className="num">{n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="card">
          <h3>Historial</h3>
          <table>
            <tbody>
              {history.slice(0, 15).map((r) => (
                <tr key={r.id}>
                  <td className="small">{dateTime(r.created_at)}</td>
                  <td>{r.invoice.number ?? r.filename}</td>
                  <td>
                    <span className={`pill dec-${r.decision}`}>{DECISION_LABEL[r.decision]}</span>
                    {r.review_status && r.review_status !== "pending" && (
                      <span className="muted small"> → humano: {r.review_status === "approved" ? "aprobó" : "rechazó"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
