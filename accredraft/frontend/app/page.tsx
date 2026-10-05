"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, Project, Template } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [description, setDescription] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [p, t] = await Promise.all([api.listProjects(), api.listTemplates()]);
      setProjects(p);
      setTemplates(t);
      if (t.length && !templateId) setTemplateId(t[0].id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const project = await api.createProject(templateId, name, description || undefined);
      setProjects((prev) => [project, ...prev]);
      setName("");
      setDescription("");
      setCreating(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create project");
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Projects</h1>
          <p className="mt-1 text-sm text-slate-500">
            Each project is pinned to a template version. Evidence in, validated document out.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setCreating((v) => !v)}>
          {creating ? "Cancel" : "New project"}
        </button>
      </div>

      {error && (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      )}

      {creating && (
        <form onSubmit={create} className="card space-y-4 p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Project name</label>
              <input
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Workshop on AI Ethics — Dec 2024"
                required
              />
            </div>
            <div>
              <label className="label">Template</label>
              <select
                className="input"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                required
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.body} · {t.name} · v{t.version}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Description (optional)</label>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex justify-end">
            <button className="btn-primary" disabled={!templateId || !name}>
              Create project
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : projects.length === 0 ? (
        <div className="card p-10 text-center">
          <p className="text-sm text-slate-500">
            No projects yet. Create one to start assembling evidence.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="card group p-5 transition-shadow hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-medium text-slate-900 group-hover:text-brand-700">{p.name}</h3>
                <StatusBadge status={p.status} />
              </div>
              {p.description && (
                <p className="mt-1.5 line-clamp-2 text-sm text-slate-500">{p.description}</p>
              )}
              <p className="mt-4 font-mono text-xs text-slate-400">
                template v{p.template_version}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
