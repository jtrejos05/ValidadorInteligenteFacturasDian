import type { Decision } from "./api";

const cop = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

export const money = (value: string | number | null | undefined) =>
  value === null || value === undefined || value === "" ? "—" : cop.format(Number(value));

export const usd = (value: number) => `US$ ${value.toFixed(value < 0.01 ? 5 : 4)}`;

export const DECISION_LABEL: Record<Decision, string> = {
  approved: "Aprobada",
  rejected: "Rechazada",
  needs_review: "Revisión manual",
};

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
