import { useCallback, useEffect, useState } from "react";
import { api, type Report } from "../api";
import { dateTime, money } from "../format";
import { ReportView } from "./ReportView";

export function ReviewPage({ onChange }: { onChange: () => void }) {
  const [queue, setQueue] = useState<Report[]>([]);
  const [current, setCurrent] = useState<Report | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .reports("pending")
      .then((items) => {
        setQueue(items);
        setCurrent((c) => items.find((i) => i.id === c?.id) ?? items[0] ?? null);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(load, [load]);

  async function decide(decision: "approved" | "rejected") {
    if (!current) return;
    try {
      await api.review(current.id, decision, note);
      setNote("");
      setCurrent(null);
      load();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (queue.length === 0) {
    return (
      <div className="empty">
        <p>No hay facturas pendientes de revisión.</p>
        <p className="muted small">Las facturas con alertas (de reglas o de la IA) llegan aquí para que una persona decida.</p>
      </div>
    );
  }

  return (
    <div className="grid">
      <div className="panel">
        <section className="card">
          <h3>Pendientes ({queue.length})</h3>
          <ul className="queue">
            {queue.map((r) => (
              <li key={r.id}>
                <button className={`queue-item ${current?.id === r.id ? "active" : ""}`} onClick={() => setCurrent(r)}>
                  <strong>{r.invoice.number ?? r.filename}</strong>
                  <span className="muted small">
                    {r.invoice.supplier.name ?? "—"} · {money(r.invoice.payable_amount)} · {dateTime(r.created_at)}
                  </span>
                  <span className="small">{r.findings.filter((f) => f.severity !== "info").map((f) => f.code).join(", ")}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        {current && (
          <section className="card">
            <h3>Decisión humana</h3>
            <textarea placeholder="Nota para auditoría (opcional)" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="row">
              <button onClick={() => decide("approved")}>Aprobar pago</button>
              <button className="danger" onClick={() => decide("rejected")}>
                Rechazar
              </button>
            </div>
          </section>
        )}
        {error && <div className="error">{error}</div>}
      </div>
      <div className="panel">{current && <ReportView report={current} />}</div>
    </div>
  );
}
