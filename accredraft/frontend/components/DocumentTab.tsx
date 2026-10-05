"use client";

import { useEffect, useState } from "react";
import { api, ApiError, DocumentRecord, GeneratedOutput } from "@/lib/api";

export function DocumentTab({
  projectId,
  onChanged,
  onGoToValidation,
}: {
  projectId: string;
  onChanged: () => void;
  onGoToValidation: () => void;
}) {
  const [outputs, setOutputs] = useState<GeneratedOutput[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    try {
      const [o, d] = await Promise.all([
        api.listOutputs(projectId),
        api.listDocuments(projectId),
      ]);
      setOutputs(o);
      setDocuments(d);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load outputs");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function generate() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await api.generate(projectId);
      setNote(
        res.pdf_available
          ? "DOCX and PDF generated."
          : "DOCX generated. PDF unavailable — LibreOffice is not installed (see README)."
      );
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Generation failed");
    } finally {
      setBusy(false);
    }
  }

  async function download(output: GeneratedOutput) {
    try {
      const token =
        typeof window !== "undefined" ? window.localStorage.getItem("accredraft_token") : null;
      const res = await fetch(api.outputDownloadUrl(output.id), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report.${output.format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

  const latest = documents[0];

  return (
    <div className="space-y-5">
      <div className="card flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-700">Generate document</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Renders the confirmed values through the layout template. Missing values become a
            highlighted <code className="font-mono">[TO BE PROVIDED]</code> placeholder.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary !py-1.5 text-xs" onClick={onGoToValidation}>
            ← Validation
          </button>
          <button className="btn-primary !py-1.5 text-xs" onClick={generate} disabled={busy}>
            {busy ? "Generating…" : "Generate DOCX"}
          </button>
        </div>
      </div>

      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {note && <p className="rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-700">{note}</p>}

      {latest && (
        <div className="card px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Latest document version
          </p>
          <p className="mt-1 text-sm text-slate-700">
            v{latest.version} · generated {new Date(latest.created_at).toLocaleString()}
          </p>
          <p className="mt-1 font-mono text-xs text-slate-400">
            stamped with template v{String(latest.doc_model_json?.template_version ?? "")}
          </p>
        </div>
      )}

      <div className="card overflow-hidden">
        <h3 className="border-b border-slate-100 bg-slate-50/70 px-5 py-3 text-sm font-semibold text-slate-700">
          Generated outputs
        </h3>
        {outputs.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">Nothing generated yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {outputs.map((o) => (
              <li key={o.id} className="flex items-center gap-3 px-5 py-3">
                <span
                  className={`flex h-9 w-11 items-center justify-center rounded-md text-[10px] font-bold ${
                    o.format === "pdf" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"
                  }`}
                >
                  {o.format.toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-800">
                    {o.format.toUpperCase()} · template v{o.template_version}
                  </p>
                  <p className="text-xs text-slate-400">
                    {new Date(o.created_at).toLocaleString()}
                  </p>
                </div>
                <button className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => download(o)}>
                  Download
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
