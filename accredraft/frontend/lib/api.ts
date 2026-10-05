// Typed API client. Requests go to /api/* and are proxied to the backend
// by the Next.js rewrite in next.config.mjs (no CORS needed).

export const TOKEN_KEY = "accredraft_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(path, { ...init, headers });

  if (res.status === 401 && typeof window !== "undefined" && !path.includes("/auth/login")) {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ── Types ────────────────────────────────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  name: string | null;
  role: string;
  org_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TemplateField {
  id: string;
  type: string;
  required: boolean;
  label?: string;
  min_items?: number;
  min?: number;
  caption_required?: boolean;
}

export interface TemplateSection {
  id: string;
  title: string;
  fields: TemplateField[];
}

export interface ValidationRule {
  id: string;
  rule: string;
  severity: "error" | "warning";
  message: string;
}

export interface TemplateSchema {
  template_id: string;
  body: string;
  version: string;
  sections: TemplateSection[];
  validation_rules: ValidationRule[];
}

export interface Template {
  id: string;
  body: string;
  category: string;
  name: string;
  version: string;
  status: string;
  source_url: string | null;
  last_verified: string | null;
  schema_json: TemplateSchema;
  layout_template_path: string | null;
  doc_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  org_id: string | null;
  template_id: string;
  template_version: string;
  name: string;
  description: string | null;
  status: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectFile {
  id: string;
  project_id: string;
  filename: string;
  mime: string;
  sha256: string | null;
  page_count: number | null;
  file_kind: string | null;
  created_at: string;
}

export interface FieldSource {
  id: string;
  evidence_item_id: string;
  snippet: string | null;
  file_name: string | null;
  page: number | null;
}

export interface ExtractedField {
  id: string;
  project_id: string;
  section_id: string;
  field_id: string;
  value_json: unknown;
  confidence: number | null;
  status: string;
  edited_by: string | null;
  edited_at: string | null;
  created_at: string;
  sources: FieldSource[];
  label: string | null;
}

export interface ValidationResult {
  id: string;
  rule_id: string;
  field_id: string | null;
  status: "ok" | "error" | "warning";
  message: string | null;
  details: Record<string, unknown> | null;
}

export interface ValidationRun {
  id: string;
  project_id: string;
  template_version: string;
  run_at: string;
  results: ValidationResult[];
}

export interface GeneratedOutput {
  id: string;
  document_id: string;
  format: string;
  storage_key: string;
  template_version: string;
  created_at: string;
}

export interface DocumentRecord {
  id: string;
  project_id: string;
  doc_model_json: Record<string, unknown>;
  version: number;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  user_id: string | null;
  project_id: string | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ts: string;
}

// ── Endpoints ────────────────────────────────────────────────────────────────
export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string, name: string, org_name?: string) =>
    request<User>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name, org_name }),
    }),

  me: () => request<User>("/api/auth/me"),

  listTemplates: () => request<Template[]>("/api/templates"),
  getTemplate: (id: string) => request<Template>(`/api/templates/${id}`),

  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (template_id: string, name: string, description?: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ template_id, name, description }),
    }),
  deleteProject: (id: string) =>
    request<{ message: string }>(`/api/projects/${id}`, { method: "DELETE" }),

  listFiles: (projectId: string) => request<ProjectFile[]>(`/api/projects/${projectId}/files`),
  uploadFiles: (projectId: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<ProjectFile[]>(`/api/projects/${projectId}/files`, {
      method: "POST",
      body: form,
    });
  },
  deleteFile: (fileId: string) =>
    request<{ message: string }>(`/api/files/${fileId}`, { method: "DELETE" }),
  getEvidence: (fileId: string) =>
    request<
      {
        id: string;
        file_id: string;
        filename: string | null;
        page: number | null;
        item_type: string;
        raw_text: string | null;
        image_caption: string | null;
        classification: string | null;
        ocr_confidence: number | null;
      }[]
    >(`/api/files/${fileId}/evidence`),

  process: (projectId: string) =>
    request<{ message: string }>(`/api/projects/${projectId}/process`, { method: "POST" }),
  extract: (projectId: string) =>
    request<{ message: string }>(`/api/projects/${projectId}/extract`, { method: "POST" }),
  listExtractions: (projectId: string) =>
    request<ExtractedField[]>(`/api/projects/${projectId}/extractions`),
  updateExtraction: (projectId: string, fieldId: string, value: unknown, status?: string) =>
    request<ExtractedField>(`/api/projects/${projectId}/extractions/${fieldId}`, {
      method: "PUT",
      body: JSON.stringify({ value, status }),
    }),

  validate: (projectId: string) =>
    request<{ ok: number; errors: number; warnings: number }>(
      `/api/projects/${projectId}/validate/sync`,
      { method: "POST" }
    ),
  getValidation: (projectId: string) =>
    request<ValidationRun>(`/api/projects/${projectId}/validation`),

  generate: (projectId: string) =>
    request<{ document_id: string; docx_key: string; pdf_key: string | null; pdf_available: boolean }>(
      `/api/projects/${projectId}/generate/sync`,
      { method: "POST" }
    ),
  listOutputs: (projectId: string) =>
    request<GeneratedOutput[]>(`/api/projects/${projectId}/outputs`),
  outputDownloadUrl: (outputId: string) => `/api/outputs/${outputId}/download`,

  listDocuments: (projectId: string) =>
    request<DocumentRecord[]>(`/api/projects/${projectId}/documents`),
  projectAudit: (projectId: string) => request<AuditEntry[]>(`/api/projects/${projectId}/audit`),
};
