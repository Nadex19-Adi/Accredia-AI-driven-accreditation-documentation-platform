"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError, ExtractedField, Project, ProjectFile, Template } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EvidenceTab } from "@/components/EvidenceTab";
import { ReviewTab } from "@/components/ReviewTab";
import { ValidationTab } from "@/components/ValidationTab";
import { DocumentTab } from "@/components/DocumentTab";
import { AuditTab } from "@/components/AuditTab";

type Tab = "evidence" | "review" | "validation" | "document" | "audit";

const TABS: { id: Tab; label: string }[] = [
  { id: "evidence", label: "Evidence" },
  { id: "review", label: "Extraction review" },
  { id: "validation", label: "Validation" },
  { id: "document", label: "Document" },
  { id: "audit", label: "Audit log" },
];

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [template, setTemplate] = useState<Template | null>(null);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [fields, setFields] = useState<ExtractedField[]>([]);
  const [tab, setTab] = useState<Tab>("evidence");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const p = await api.getProject(projectId);
      setProject(p);
      const [t, f, x] = await Promise.all([
        api.getTemplate(p.template_id),
        api.listFiles(projectId),
        api.listExtractions(projectId),
      ]);
      setTemplate(t);
      setFiles(f);
      setFields(x);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (loading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (error) return <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>;
  if (!project) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <button
            onClick={() => router.push("/")}
            className="mb-2 text-sm text-slate-500 hover:text-slate-700"
          >
            ← Projects
          </button>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">{project.name}</h1>
            <StatusBadge status={project.status} />
          </div>
          {template && (
            <p className="mt-1.5 text-sm text-slate-500">
              {template.body} · {template.name} ·{" "}
              <span className="font-mono">v{project.template_version}</span>{" "}
              <span className="text-slate-400">(pinned at creation)</span>
            </p>
          )}
        </div>
      </div>

      <div className="border-b border-slate-200">
        <nav className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                tab === t.id
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700"
              }`}
            >
              {t.label}
              {t.id === "review" && fields.length > 0 && (
                <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
                  {fields.filter((f) => f.status === "auto").length} to review
                </span>
              )}
              {t.id === "evidence" && files.length > 0 && (
                <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
                  {files.length}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {tab === "evidence" && (
        <EvidenceTab projectId={projectId} files={files} onChanged={refresh} />
      )}
      {tab === "review" && (
        <ReviewTab
          projectId={projectId}
          fields={fields}
          template={template}
          onChanged={refresh}
          onGoToValidation={() => setTab("validation")}
        />
      )}
      {tab === "validation" && (
        <ValidationTab projectId={projectId} onChanged={refresh} onGoToReview={() => setTab("review")} />
      )}
      {tab === "document" && (
        <DocumentTab projectId={projectId} onChanged={refresh} onGoToValidation={() => setTab("validation")} />
      )}
      {tab === "audit" && <AuditTab projectId={projectId} />}
    </div>
  );
}
