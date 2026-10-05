"use client";

import { useRef, useState } from "react";
import { api, ApiError, ProjectFile } from "@/lib/api";

const KIND_ICON: Record<string, string> = {
  pdf: "PDF",
  docx: "DOC",
  image: "IMG",
  xlsx: "XLS",
  unknown: "FILE",
};

const KIND_COLOR: Record<string, string> = {
  pdf: "bg-red-50 text-red-600",
  docx: "bg-blue-50 text-blue-600",
  image: "bg-purple-50 text-purple-600",
  xlsx: "bg-emerald-50 text-emerald-600",
  unknown: "bg-slate-100 text-slate-500",
};

export function EvidenceTab({
  projectId,
  files,
  onChanged,
}: {
  projectId: string;
  files: ProjectFile[];
  onChanged: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<{ file: ProjectFile; items: any[] } | null>(null);

  async function upload(fileList: FileList | File[]) {
    const list = Array.from(fileList);
    if (!list.length) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.uploadFiles(projectId, list);
      setMessage(`Uploaded ${list.length} file(s).`);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function process() {
    setBusy(true);
    setError(null);
    setMessage("Parsing files…");
    try {
      await api.process(projectId);
      // Background task: poll until evidence shows up.
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const current = await api.listFiles(projectId);
        if (current.some((f) => f.page_count !== null)) break;
      }
      setMessage("Parsing complete. Next: run extraction on the Review tab.");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Processing failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(file: ProjectFile) {
    if (!confirm(`Delete ${file.filename}?`)) return;
    try {
      await api.deleteFile(file.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    }
  }

  async function showEvidence(file: ProjectFile) {
    try {
      const items = await api.getEvidence(file.id);
      setPreview({ file, items });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load evidence");
    }
  }

  return (
    <div className="space-y-5">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          upload(e.dataTransfer.files);
        }}
        className={`card flex flex-col items-center justify-center border-2 border-dashed px-6 py-12 text-center transition-colors ${
          dragging ? "border-brand-400 bg-brand-50/50" : "border-slate-200"
        }`}
      >
        <p className="text-sm font-medium text-slate-700">
          Drop evidence files here, or{" "}
          <button className="text-brand-600 hover:underline" onClick={() => inputRef.current?.click()}>
            browse
          </button>
        </p>
        <p className="mt-1 text-xs text-slate-500">
          PDF, DOCX, JPG/PNG, XLSX · up to 50 MB each
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          accept=".pdf,.docx,.doc,.jpg,.jpeg,.png,.xlsx,.xls"
          onChange={(e) => e.target.files && upload(e.target.files)}
        />
      </div>

      {(message || error) && (
        <p
          className={`rounded-lg px-4 py-3 text-sm ${
            error ? "bg-red-50 text-red-700" : "bg-brand-50 text-brand-700"
          }`}
        >
          {error ?? message}
        </p>
      )}

      <div className="card">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="text-sm font-semibold text-slate-700">
            Files <span className="text-slate-400">({files.length})</span>
          </h3>
          <button className="btn-primary !py-1.5 text-xs" onClick={process} disabled={busy || !files.length}>
            {busy ? "Working…" : "Process files"}
          </button>
        </div>

        {files.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">No files uploaded yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {files.map((f) => (
              <li key={f.id} className="flex items-center gap-3 px-5 py-3">
                <span
                  className={`flex h-9 w-11 shrink-0 items-center justify-center rounded-md text-[10px] font-bold ${
                    KIND_COLOR[f.file_kind ?? "unknown"]
                  }`}
                >
                  {KIND_ICON[f.file_kind ?? "unknown"]}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">{f.filename}</p>
                  <p className="font-mono text-xs text-slate-400">
                    {f.page_count ? `${f.page_count} page(s)` : "not parsed yet"}
                    {f.sha256 ? ` · ${f.sha256.slice(0, 10)}` : ""}
                  </p>
                </div>
                <button className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => showEvidence(f)}>
                  View parsed
                </button>
                <button className="btn-danger !px-2.5 !py-1 text-xs" onClick={() => remove(f)}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {preview && (
        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
            <h3 className="text-sm font-semibold text-slate-700">
              Parsed evidence — {preview.file.filename}{" "}
              <span className="text-slate-400">({preview.items.length} items)</span>
            </h3>
            <button className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => setPreview(null)}>
              Close
            </button>
          </div>
          {preview.items.length === 0 ? (
            <p className="px-5 py-6 text-sm text-slate-500">
              Nothing parsed yet — click “Process files”.
            </p>
          ) : (
            <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
              {preview.items.slice(0, 200).map((item) => (
                <li key={item.id} className="px-5 py-2.5">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="badge bg-slate-100 text-slate-600">{item.item_type}</span>
                    {item.page && <span className="text-xs text-slate-400">page {item.page}</span>}
                    {item.classification && (
                      <span className="badge bg-purple-50 text-purple-600">{item.classification}</span>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap font-mono text-xs text-slate-600">
                    {(item.raw_text ?? item.image_caption ?? "").slice(0, 400)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
