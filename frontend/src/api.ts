// Typed client for the FastAPI backend. Types mirror backend/app/models.py.

export type Severity = "error" | "warning" | "info";
export type Decision = "approved" | "rejected" | "needs_review";

export interface Finding {
  code: string;
  severity: Severity;
  source: "rule" | "ai";
  message: string;
  field: string | null;
  expected: string | null;
  actual: string | null;
  confidence: number | null;
}

export interface LLMCall {
  purpose: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  cost_usd: number;
  error: string | null;
}

export interface InvoiceLine {
  id: string;
  description: string;
  quantity: string;
  unit_price: string;
  line_extension_amount: string;
}

export interface Invoice {
  source: string;
  number: string | null;
  cufe: string | null;
  issue_date: string | null;
  currency: string | null;
  supplier: { name: string | null; nit: string | null; check_digit: string | null };
  customer: { name: string | null; nit: string | null };
  lines: InvoiceLine[];
  line_extension_amount: string | null;
  tax_inclusive_amount: string | null;
  payable_amount: string | null;
}

export interface Report {
  id: string;
  created_at: string;
  filename: string | null;
  invoice: Invoice;
  findings: Finding[];
  decision: Decision;
  decision_reason: string;
  explanation: { summary: string; actions: string[]; risk_level: string } | null;
  llm_calls: LLMCall[];
  duration_ms: number;
  review_status: string | null;
  reviewer_note: string | null;
}

export interface Sample {
  name: string;
  description: string;
  has_xml: boolean;
  has_pdf: boolean;
  expected_decision: Decision;
}

export interface Metrics {
  invoices: number;
  by_decision: Record<Decision, number>;
  auto_resolution_rate: number;
  pending_reviews: number;
  avg_duration_ms: number;
  llm: {
    calls: number;
    errors: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    cost_per_invoice_usd: number;
    avg_latency_ms: number;
  };
  top_findings: [string, number][];
  business_case: {
    assumption_manual_minutes_per_invoice: number;
    assumption_analyst_cost_cop_per_hour: number;
    estimated_hours_saved: number;
    estimated_cop_saved: number;
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ llm_provider: string; llm_model: string }>("/health"),
  samples: () => request<Sample[]>("/samples"),
  validateSample: (name: string) =>
    request<Report>(`/samples/${encodeURIComponent(name)}/validate`, { method: "POST" }),
  validate: (xml: File | null, attachment: File | null) => {
    const form = new FormData();
    if (xml) form.append("xml", xml);
    if (attachment) form.append("attachment", attachment);
    return request<Report>("/validate", { method: "POST", body: form });
  },
  reports: (reviewStatus?: string) =>
    request<Report[]>(`/reports${reviewStatus ? `?review_status=${reviewStatus}` : ""}`),
  review: (id: string, decision: "approved" | "rejected", note: string) =>
    request<Report>(`/reports/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, note }),
    }),
  metrics: () => request<Metrics>("/metrics"),
};
