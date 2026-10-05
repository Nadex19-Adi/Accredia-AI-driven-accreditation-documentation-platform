"use client";

import { useEffect, useState } from "react";
import { api, ApiError, ValidationRun } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export function ValidationTab({
  projectId,
  onChanged,
  onGoToReview,
}: {
  projectId: string;
  onChanged: () => void;
  onGoToReview: () => void;
}) {
  const [run, setRun] = useState<ValidationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  async function load() {
    try {
      setRun(await api.getValidation(projectId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setRun(null);
      else setError(err instanceof ApiError ? err.message : "Failed to load");
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function validate() {
    setBusy(true);
    setError(null);
    try {
      await api.validate(projectId);
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Validation failed");
    } finally {
      setBusy(false);
    }
  }

  const results = run?.results ?? [];
  const errors = results.filter((r) => r.status === "error");
  const warnings = results.filter((r) => r.status === "warning");
  const oks = results.filter((r) => r.status === "ok");

  return (
    <div className="space-y-5">
      <div className="card flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-700">Validation</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Rules run in code against your confirmed values — not by the model.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary !py-1.5 text-xs" onClick={onGoToReview}>
            ← Back to review
          </button>
          <button className="btn-primary !py-1.5 text-xs" onClick={validate} disabled={busy}>
            {busy ? "Running…" : run ? "Re-run validation" : "Run validation"}
          </button>
        </div>
      </div>

      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      {loaded && !run && (
        <div className="card p-10 text-center">
          <p className="text-sm text-slate-500">No validation run yet.</p>
        </div>
      )}

      {run && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Errors", value: errors.length, tone: "text-red-600" },
              { label: "Warnings", value: warnings.length, tone: "text-amber-600" },
              { label: "Passed", value: oks.length, tone: "text-emerald-600" },
            ].map((s) => (
              <div key={s.label} className="card px-5 py-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{s.label}</p>
                <p className={`mt-1 text-2xl font-semibold ${s.tone}`}>{s.value}</p>
              </div>
            ))}
          </div>

          {errors.length > 0 && (
            <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
              Fix the errors before generating. Gaps that are genuinely unavailable should be marked
              “N/A” — they will render as a highlighted placeholder, not silently pass.
            </p>
          )}

          <div className="card overflow-hidden">
            <ul className="divide-y divide-slate-100">
              {results.map((r) => (
                <li key={r.id} className="flex items-start gap-3 px-5 py-3">
                  <span className="mt-0.5">
                    <StatusBadge
                      status={r.status}
                      label={r.status === "ok" ? "OK" : r.status === "error" ? "ERROR" : "WARNING"}
                    />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-700">{r.message}</p>
                    <p className="mt-0.5 font-mono text-xs text-slate-400">
                      {r.rule_id}
                      {r.field_id ? ` · ${r.field_id}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
