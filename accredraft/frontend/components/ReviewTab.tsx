"use client";

import { useMemo, useState } from "react";
import { api, ApiError, ExtractedField, Template } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join("\n");
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function parseValue(raw: string, type: string): unknown {
  const trimmed = raw.trim();
  if (type.endsWith("[]") || type === "integer") {
    return trimmed
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => (type === "integer" ? Number(line) : line));
  }
  if (type === "integer") return Number(trimmed);
  return trimmed;
}

export function ReviewTab({
  projectId,
  fields,
  template,
  onChanged,
  onGoToValidation,
}: {
  projectId: string;
  fields: ExtractedField[];
  template: Template | null;
  onChanged: () => void;
  onGoToValidation: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const fieldTypes = useMemo(() => {
    const map: Record<string, string> = {};
    template?.schema_json.sections.forEach((s) =>
      s.fields.forEach((f) => {
        map[`${s.id}/${f.id}`] = f.type;
      })
    );
    return map;
  }, [template]);

  const sections = useMemo(() => {
    if (!template) return [];
    return template.schema_json.sections.map((section) => ({
      section,
      fields: fields
        .filter((f) => f.section_id === section.id)
        .sort(
          (a, b) =>
            section.fields.findIndex((x) => x.id === a.field_id) -
            section.fields.findIndex((x) => x.id === b.field_id)
        ),
    }));
  }, [template, fields]);

  async function runExtraction() {
    setBusy(true);
    setError(null);
    try {
      await api.extract(projectId);
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const current = await api.listExtractions(projectId);
        if (current.some((f) => f.status !== "missing" || f.confidence !== null)) break;
      }
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Extraction failed");
    } finally {
      setBusy(false);
    }
  }

  async function save(field: ExtractedField, value: unknown, status: string) {
    setError(null);
    try {
      await api.updateExtraction(projectId, field.id, value, status);
      setEditing(null);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update failed");
    }
  }

  const pending = fields.filter((f) => f.status === "auto").length;
  const missing = fields.filter((f) => f.status === "missing").length;

  return (
    <div className="space-y-5">
      <div className="card flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-700">Extracted fields</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Confirm, edit, or mark “not available”. A missing value stays null and is never invented.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {fields.length > 0 && (
            <span className="text-xs text-slate-500">
              <span className="font-medium text-slate-700">{pending}</span> to review ·{" "}
              <span className="font-medium text-red-600">{missing}</span> missing
            </span>
          )}
          <button className="btn-secondary !py-1.5 text-xs" onClick={runExtraction} disabled={busy}>
            {busy ? "Extracting…" : fields.length ? "Re-run extraction" : "Run extraction"}
          </button>
          <button className="btn-primary !py-1.5 text-xs" onClick={onGoToValidation}>
            Validate →
          </button>
        </div>
      </div>

      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      {fields.length === 0 ? (
        <div className="card p-10 text-center">
          <p className="text-sm text-slate-500">
            No extraction yet. Upload and process evidence first, then run extraction.
          </p>
        </div>
      ) : (
        sections.map(({ section, fields: sectionFields }) => (
          <div key={section.id} className="card overflow-hidden">
            <h3 className="border-b border-slate-100 bg-slate-50/70 px-5 py-3 text-sm font-semibold text-slate-700">
              {section.title}
            </h3>
            <ul className="divide-y divide-slate-100">
              {sectionFields.map((field) => {
                const type = fieldTypes[`${field.section_id}/${field.field_id}`] ?? "string";
                const isEditing = editing === field.id;
                const isOpen = expanded === field.id;
                return (
                  <li key={field.id} className="px-5 py-3.5">
                    <div className="flex flex-wrap items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-slate-700">
                            {field.label ?? field.field_id}
                          </span>
                          <StatusBadge status={field.status} />
                          {field.confidence !== null && (
                            <span className="text-xs text-slate-400">
                              confidence {Math.round((field.confidence ?? 0) * 100)}%
                            </span>
                          )}
                          {field.sources.length > 0 && (
                            <button
                              className="text-xs text-brand-600 hover:underline"
                              onClick={() => setExpanded(isOpen ? null : field.id)}
                            >
                              {field.sources.length} source{field.sources.length > 1 ? "s" : ""}
                            </button>
                          )}
                        </div>

                        {isEditing ? (
                          <div className="mt-2 space-y-2">
                            <textarea
                              className="input font-mono text-xs"
                              rows={type.endsWith("[]") ? 3 : 2}
                              value={draft}
                              onChange={(e) => setDraft(e.target.value)}
                              placeholder={type.endsWith("[]") ? "one item per line" : ""}
                            />
                            <div className="flex gap-2">
                              <button
                                className="btn-primary !py-1 text-xs"
                                onClick={() => save(field, parseValue(draft, type), "edited")}
                              >
                                Save as edited
                              </button>
                              <button
                                className="btn-secondary !py-1 text-xs"
                                onClick={() => setEditing(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p
                            className={`mt-1 whitespace-pre-wrap font-mono text-xs ${
                              field.value_json === null ? "italic text-slate-400" : "text-slate-700"
                            }`}
                          >
                            {field.value_json === null ? "null (not found)" : renderValue(field.value_json)}
                          </p>
                        )}

                        {isOpen && field.sources.length > 0 && (
                          <div className="mt-2 space-y-1.5 rounded-lg bg-slate-50 p-3">
                            {field.sources.map((s) => (
                              <p key={s.id} className="text-xs text-slate-600">
                                <span className="font-medium">
                                  {s.file_name}
                                  {s.page ? ` · page ${s.page}` : ""}
                                </span>
                                <span className="mt-0.5 block font-mono text-slate-500">
                                  “{s.snippet}”
                                </span>
                              </p>
                            ))}
                          </div>
                        )}
                      </div>

                      {!isEditing && (
                        <div className="flex shrink-0 gap-1.5">
                          {field.status !== "confirmed" && field.value_json !== null && (
                            <button
                              className="btn-secondary !px-2 !py-1 text-xs"
                              onClick={() => save(field, field.value_json, "confirmed")}
                            >
                              Confirm
                            </button>
                          )}
                          <button
                            className="btn-secondary !px-2 !py-1 text-xs"
                            onClick={() => {
                              setEditing(field.id);
                              setDraft(renderValue(field.value_json));
                            }}
                          >
                            Edit
                          </button>
                          {field.status !== "na" && (
                            <button
                              className="btn-secondary !px-2 !py-1 text-xs"
                              onClick={() => save(field, null, "na")}
                              title="Mark as not available"
                            >
                              N/A
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}
