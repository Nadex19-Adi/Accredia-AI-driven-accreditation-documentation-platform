"use client";

import { useEffect, useState } from "react";
import { api, ApiError, AuditEntry } from "@/lib/api";

export function AuditTab({ projectId }: { projectId: string }) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .projectAudit(projectId)
      .then(setEntries)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load audit log"))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (error) return <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>;

  return (
    <div className="card overflow-hidden">
      <h3 className="border-b border-slate-100 bg-slate-50/70 px-5 py-3 text-sm font-semibold text-slate-700">
        Audit log — every change is traceable
      </h3>
      {entries.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-slate-500">No activity recorded yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {entries.map((e) => (
            <li key={e.id} className="px-5 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="badge bg-slate-100 text-slate-700">{e.action}</span>
                <span className="text-xs text-slate-400">{new Date(e.ts).toLocaleString()}</span>
              </div>
              {(e.before || e.after) && (
                <pre className="mt-1.5 overflow-x-auto rounded-lg bg-slate-50 p-2.5 font-mono text-[11px] text-slate-600">
                  {e.before ? `before: ${JSON.stringify(e.before)}` : ""}
                  {e.before && e.after ? "\n" : ""}
                  {e.after ? `after:  ${JSON.stringify(e.after)}` : ""}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
