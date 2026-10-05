const STYLES: Record<string, string> = {
  ok: "bg-emerald-50 text-emerald-700",
  error: "bg-red-50 text-red-700",
  warning: "bg-amber-50 text-amber-700",
  confirmed: "bg-emerald-50 text-emerald-700",
  edited: "bg-blue-50 text-blue-700",
  auto: "bg-slate-100 text-slate-600",
  missing: "bg-red-50 text-red-700",
  na: "bg-slate-100 text-slate-500",
  draft: "bg-slate-100 text-slate-600",
  processing: "bg-amber-50 text-amber-700",
  review: "bg-blue-50 text-blue-700",
  validated: "bg-emerald-50 text-emerald-700",
  generated: "bg-brand-50 text-brand-700",
  active: "bg-emerald-50 text-emerald-700",
  verified: "bg-emerald-50 text-emerald-700",
  superseded: "bg-amber-50 text-amber-700",
  deprecated: "bg-slate-100 text-slate-500",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const cls = STYLES[status] ?? "bg-slate-100 text-slate-600";
  return <span className={`badge ${cls}`}>{label ?? status}</span>;
}
