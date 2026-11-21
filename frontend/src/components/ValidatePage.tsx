import { useEffect, useState } from "react";
import { api, type Report, type Sample } from "../api";
import { DECISION_LABEL } from "../format";
import { ReportView } from "./ReportView";

export function ValidatePage() {
  const [xml, setXml] = useState<File | null>(null);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [sample, setSample] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);

  async function run(task: () => Promise<Report>) {
    setBusy(true);
    setError(null);
    try {
      setReport(await task());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const selected = samples.find((s) => s.name === sample);

  return (
    <div className="grid">
      <div className="panel">
        <section className="card">
          <h3>Subir factura</h3>
          <label className="file">
            <span>XML de la factura (UBL 2.1)</span>
            <input type="file" accept=".xml,application/xml,text/xml" onChange={(e) => setXml(e.target.files?.[0] ?? null)} />
          </label>
          <label className="file">
            <span>Representación gráfica (PDF o imagen, opcional)</span>
            <input
              type="file"
              accept="application/pdf,image/png,image/jpeg,image/webp"
              onChange={(e) => setAttachment(e.target.files?.[0] ?? null)}
            />
          </label>
          <button disabled={busy || (!xml && !attachment)} onClick={() => run(() => api.validate(xml, attachment))}>
            {busy ? "Validando…" : "Validar"}
          </button>
        </section>

        <section className="card">
          <h3>O probar con una factura de ejemplo</h3>
          <select value={sample} onChange={(e) => setSample(e.target.value)}>
            <option value="">Elegir ejemplo…</option>
            {samples.map((s) => (
              <option key={s.name} value={s.name}>
                {s.description}
              </option>
            ))}
          </select>
          {selected && (
            <p className="muted small">
              Resultado esperado: {DECISION_LABEL[selected.expected_decision]} ·{" "}
              {selected.has_xml && <a href={`/api/samples/${selected.name}/xml`}>descargar XML</a>}
              {selected.has_xml && selected.has_pdf && " · "}
              {selected.has_pdf && <a href={`/api/samples/${selected.name}/pdf`}>descargar PDF</a>}
            </p>
          )}
          <button className="secondary" disabled={busy || !sample} onClick={() => run(() => api.validateSample(sample))}>
            Validar ejemplo
          </button>
        </section>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="panel">
        {report ? (
          <ReportView report={report} />
        ) : (
          <div className="empty">
            <p>Sube un XML o elige un ejemplo para ver el reporte.</p>
            <p className="muted small">
              Las reglas DIAN (CUFE, NIT, totales, IVA, resolución) se verifican con código determinista. La IA lee el
              PDF, revisa si la tarifa de IVA tiene sentido para cada producto y explica el resultado.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
