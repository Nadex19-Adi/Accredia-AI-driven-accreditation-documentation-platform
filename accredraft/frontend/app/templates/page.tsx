"use client";

import { useEffect, useState } from "react";
import { api, ApiError, Template } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    api
      .listTemplates()
      .then(setTemplates)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">Template registry</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          A template has two layers: a <strong>requirement schema</strong> (what must be provided —
          used for validation) and an optional <strong>layout .docx</strong> (how it looks).
          Templates are hand-curated from official documents and signed off by an admin; nothing is
          auto-scraped.
        </p>
      </div>

      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <div className="space-y-3">
          {templates.map((t) => {
            const open = openId === t.id;
            const schema = t.schema_json;
            return (
              <div key={t.id} className="card overflow-hidden">
                <button
                  onClick={() => setOpenId(open ? null : t.id)}
                  className="flex w-full flex-wrap items-center gap-3 px-5 py-4 text-left hover:bg-slate-50"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-xs font-bold text-brand-700">
                    {t.body}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-slate-900">{t.name}</span>
                    <span className="block font-mono text-xs text-slate-400">
                      {schema?.template_id ?? t.id} · v{t.version}
                      {t.layout_template_path ? " · has layout .docx" : " · renderer default layout"}
                    </span>
                  </span>
                  <StatusBadge status={t.status} />
                  <span className="text-slate-400">{open ? "▲" : "▼"}</span>
                </button>

                {open && schema && (
                  <div className="border-t border-slate-100 bg-slate-50/60 px-5 py-4">
                    <div className="grid gap-6 lg:grid-cols-2">
                      <div>
                        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Required fields
                        </h4>
                        <div className="space-y-3">
                          {schema.sections.map((section) => (
                            <div key={section.id}>
                              <p className="text-sm font-medium text-slate-700">{section.title}</p>
                              <ul className="mt-1 space-y-0.5">
                                {section.fields.map((f) => (
                                  <li key={f.id} className="flex items-center gap-2 text-sm">
                                    <code className="font-mono text-xs text-slate-500">{f.id}</code>
                                    <span className="text-slate-400">{f.type}</span>
                                    {f.required && (
                                      <span className="badge bg-red-50 text-red-600">required</span>
                                    )}
                                    {f.min_items ? (
                                      <span className="text-xs text-slate-400">
                                        min {f.min_items}
                                      </span>
                                    ) : null}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div>
                        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Validation rules (evaluated in code)
                        </h4>
                        <ul className="space-y-1.5">
                          {schema.validation_rules.map((r) => (
                            <li key={r.id} className="text-sm">
                              <code className="rounded bg-white px-1.5 py-0.5 font-mono text-xs text-slate-700">
                                {r.rule}
                              </code>
                              <StatusBadge status={r.severity} />
                              <span className="ml-2 text-slate-500">{r.message}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
