import { useEffect, useState } from "react";
import { api } from "./api";
import { MetricsPage } from "./components/MetricsPage";
import { ReviewPage } from "./components/ReviewPage";
import { ValidatePage } from "./components/ValidatePage";

type Tab = "validate" | "review" | "metrics";

export default function App() {
  const [tab, setTab] = useState<Tab>("validate");
  const [provider, setProvider] = useState<string>("…");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api
      .health()
      .then((h) => setProvider(h.llm_provider === "mock" ? "IA simulada (sin API key)" : `Claude · ${h.llm_model}`))
      .catch(() => setProvider("backend no disponible"));
  }, []);

  const tabs: [Tab, string][] = [
    ["validate", "Validar"],
    ["review", "Revisión manual"],
    ["metrics", "Métricas"],
  ];

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="logo">✓</span>
          <div>
            <h1>Validador Inteligente de Facturas DIAN</h1>
            <p className="muted small">Factura electrónica UBL 2.1 · reglas deterministas + IA</p>
          </div>
        </div>
        <span className="provider">{provider}</span>
      </header>
      <nav>
        {tabs.map(([id, label]) => (
          <button key={id} className={`tab ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>
      <main>
        {tab === "validate" && <ValidatePage />}
        {tab === "review" && <ReviewPage onChange={() => setRefreshKey((k) => k + 1)} />}
        {tab === "metrics" && <MetricsPage refreshKey={refreshKey} />}
      </main>
    </div>
  );
}
