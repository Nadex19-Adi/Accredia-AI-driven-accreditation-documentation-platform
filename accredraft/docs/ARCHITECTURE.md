# Architecture

How AccreditDraft is put together, and where each design rule is actually enforced in code.

---

## Scope boundary

AccreditDraft implements **the evidence-to-document step only**:

```
messy files  →  parsed evidence  →  typed fields + provenance  →  human review
             →  code validation  →  DOCX / PDF
```

It does **not**:

- judge whether evidence satisfies an accreditation criterion
- compute NAAC/NBA metrics
- decide whether an institution deserves accreditation
- decide what a template requires (a human writes the schema)
- decide whether a document is complete (the validator does)

Those exclusions are the point of the design, not missing features.

---

## The core idea

Treat it as a **compiler for accreditation documents**:

| Compiler concept | AccreditDraft |
|---|---|
| Source code | the uploaded evidence files |
| Grammar + type system | the template's requirement schema |
| Parser | the LLM extractor (fills typed fields, records provenance) |
| Type checker | `services/validator.py` — pure code, no model |
| Human patch | the review UI (confirm / edit / mark N/A) |
| Code generator | `services/renderer.py` — DOCX and PDF |

The AI is deliberately only the **parser**. Adding a new accreditation body means adding a new
grammar file, not retraining or re-prompting anything.

---

## Layers

```
Next.js UI  (app/, components/, lib/api.ts)
   │  REST over /api/*, proxied by the Next rewrite (no CORS in practice)
   │
FastAPI  (app/api/*  — 8 routers, prefix /api)
   │  auth (JWT) · projects · templates · files · extraction · validation · documents · audit
   │
Pipeline  (app/services/pipeline.py)
   ├─ 1 ingest    process_files()      parse PDF/DOCX/XLSX/images → evidence_items
   ├─ 2 extract   run_extraction()     schema-constrained LLM → extracted_fields + field_sources
   ├─ 3 validate  run_validation()     template rules in code → validation_runs/results
   └─ 4 render    generate_document()  document model → DOCX → (LibreOffice) PDF
   │
SQLAlchemy → SQLite (default) or PostgreSQL   ·   local disk (default) or S3/MinIO
```

Each pipeline stage opens its **own DB session**, so it is safe to run outside a request — from
FastAPI `BackgroundTasks`, from an RQ worker, or inline from a `/sync` endpoint.

---

## Module map

### Backend — `backend/app/`

| Module | Responsibility |
|---|---|
| `main.py` | app wiring, CORS, lifespan, seeds the demo admin + NAAC template |
| `core/config.py` | all settings, `.env`-driven |
| `core/database.py` | SQLAlchemy engine/session, `init_db()` |
| `core/security.py` | bcrypt hashing, JWT create/decode, `get_current_user`, `require_admin` |
| `models/models.py` | 13 ORM tables |
| `models/types.py` | portable `GUID` and `JSONType` (SQLite ⇄ PostgreSQL) |
| `schemas/schemas.py` | all Pydantic request/response models |
| `api/auth.py` | register, login, me |
| `api/templates.py` | template CRUD, layout upload/download, publish |
| `api/projects.py` | project CRUD, explicit template migration |
| `api/files.py` | upload, list, delete, evidence items, original download |
| `api/extractions.py` | pipeline triggers, review list, field edit, bulk status |
| `api/validation.py` | trigger, sync run, latest run |
| `api/documents.py` | generate, sync generate, documents, outputs, download |
| `api/audit.py` | per-project and global audit log |
| `services/file_parser.py` | text/table/image extraction, OCR fallback, `get_file_kind` |
| `services/extractor.py` | LLM extraction + deterministic fallback, `ExtractionResult` |
| `services/validator.py` | rule classes and `validate_fields()` — **never calls a model** |
| `services/renderer.py` | `DocumentRenderer`, `add_page_numbers()`, `convert_docx_to_pdf()` |
| `services/pipeline.py` | the four stages + `_build_document_model()` |
| `services/storage.py` | S3/MinIO with local-disk fallback |
| `workers/rq_worker.py` | optional durable queue worker |

### Frontend — `frontend/`

| Module | Responsibility |
|---|---|
| `app/login/page.tsx` | sign-in |
| `app/page.tsx` | project list + create |
| `app/projects/[id]/page.tsx` | the 5-tab workspace |
| `app/templates/page.tsx` | template registry browser |
| `components/AppShell.tsx` | nav frame, auth guard |
| `components/EvidenceTab.tsx` | upload, process, evidence browser |
| `components/ReviewTab.tsx` | per-field confirm / edit / N/A with source snippets |
| `components/ValidationTab.tsx` | OK / ERROR / WARNING checklist |
| `components/DocumentTab.tsx` | generate + download |
| `components/AuditTab.tsx` | audit trail |
| `lib/api.ts` | typed client and all shared types |

---

## Data flow, step by step

### 1. Ingest — `process_files()`

For each file: download from storage → `parse_file()` → one `EvidenceItem` per text block, table, or
image, each carrying `page`, `bbox`, `item_type`, and (for scans) `ocr_confidence` and
`classification`. Re-running is idempotent: existing evidence for a file is deleted first.
Project status → `processing`, then `review`.

### 2. Extract — `run_extraction()`

Builds a field list from the template schema, flattens evidence text, and calls
`extract_fields()`. The prompt states the rules explicitly: extract only what is present, return
`null` when a value is not found, never invent, dates as `YYYY-MM-DD`.

Results become `ExtractedField` rows (`status = "auto"`, or `"missing"` when the value is `null`),
each with `FieldSource` rows pointing at the evidence item and quoting a snippet.

Two safeguards:

- **Human decisions are never clobbered.** Fields already in `confirmed`, `edited`, or `na` are
  skipped on re-run.
- **Every schema field exists.** Fields the model never mentions are seeded as explicit `missing`,
  so the review UI always shows the full form rather than silently omitting rows.

### 3. Validate — `run_validation()`

`build_rules_from_schema()` parses the template's `validation_rules` into rule objects;
`validate_fields()` evaluates them against current values and returns `ValidationCheck`s, persisted
as a `ValidationRun` plus `ValidationResult` rows. **No model is involved.** Project status →
`validated` only when there are zero errors.

### 4. Render — `generate_document()`

`_build_document_model()` produces the canonical **Document Model** (JSON) from the template schema
plus current field records, and stores it in `documents.doc_model_json` with an incrementing
`version`. The renderer then:

1. Uses the layout master via `docxtpl` if `template.layout_template_path` exists, otherwise builds
   a clean document with `python-docx`.
2. Adds the template id + version to the footer, and injects `PAGE` / `NUMPAGES` field codes.
3. Uploads DOCX (and PDF, if LibreOffice is available) and records `GeneratedOutput` rows.

Because the document model is format-independent, DOCX and PDF are just renderers of the same
object.

---

## The Document Model

The single canonical artifact. DOCX and PDF are both derived from it.

```json
{
  "template_id": "naac-c3-event-report",
  "template_version": "2025",
  "generated_at": "2026-10-05T20:45:00",
  "sections": [
    {
      "id": "event_basic",
      "title": "Event Details",
      "fields": {
        "title": { "value": "Workshop on AI Ethics", "status": "confirmed",
                   "confidence": 0.6, "label": "Event Title" },
        "photos": { "value": null, "status": "missing", "label": "Event Photos" }
      }
    }
  ]
}
```

Note that `status` travels with the value into the document model. That is what lets the renderer
decide, per field, between a real value and `[TO BE PROVIDED]`.

---

## Two layers per template — never mixed

**A. Requirement schema** (`templates.schema_json`) — *what must be provided*. Drives both
extraction and validation:

```json
{
  "template_id": "naac-c3-event-report",
  "body": "NAAC",
  "version": "2025",
  "sections": [
    { "id": "event_basic", "title": "Event Details", "fields": [
      { "id": "title", "type": "string",  "required": true, "label": "Event Title" },
      { "id": "date",  "type": "date",    "required": true, "label": "Event Date" },
      { "id": "photos", "type": "image[]", "required": true, "min": 2,
        "caption_required": true, "label": "Event Photos" }
    ]}
  ],
  "validation_rules": [
    { "id": "r1", "rule": "date <= today", "severity": "error",
      "message": "Event date cannot be in the future" },
    { "id": "r3", "rule": "photos.length >= 2", "severity": "error",
      "message": "At least 2 supporting photographs are required" }
  ]
}
```

Field types in use: `string`, `date`, `integer`, `text`, `text[]`, `image[]`, `file`.

**B. Layout template** (`templates.layout_template_path`) — *how it looks*. A real `.docx` master
with styles, filled by `docxtpl`. Filling a human-made master is far more reliable than generating
layout from scratch, so that is the primary path and the from-scratch renderer is the fallback.

The rule language is deliberately tiny — comparisons, dates, collection length. It must not grow
into a programming language.

---

## Design rules → where they are enforced

| Rule | Enforcement point | Status |
|---|---|---|
| Extraction and drafting are separate; facts are confirmed before prose | review step precedes generation | yes |
| A missing value is `null` — "not found" is a valid answer | `extractor.py` prompt + `run_extraction` | yes |
| The LLM never decides completeness | `services/validator.py` (pure code) | yes |
| Every extracted value carries provenance | `field_sources` table | **only in LLM mode** — the regex fallback emits no sources |
| Missing values render visibly as `[TO BE PROVIDED]` | `renderer.MISSING_PLACEHOLDER` | yes, when the value is `null` |
| Template version is pinned per project | `projects.template_version`, set at creation | yes |
| Template migration is explicit, never automatic | `POST /projects/{id}/migrate` | yes |
| Every human edit is audited | `audit_log` via `field.update`, `files.upload`, … | yes |
| Only confirmed values reach the document | `renderer._render_field` | **no — see below** |

### Where the implementation is narrower than the intent

These are verified gaps between the documentation and the code, listed rather than glossed over.

1. **Unconfirmed values reach the document.** `_render_field` and `_build_template_context` render a
   value when `value is not None and status != "missing"`. A field left in `auto` (never reviewed)
   and a field marked `na` that still carries a value will both be printed as if they were
   confirmed. The safe rule — render only `confirmed` / `edited`, treat `auto` and `na` as missing —
   is not implemented.

2. **Generation does not re-check template status.** `create_project` refuses templates that are not
   `active`/`verified`, but `generate_document` uses `project.template_id` without re-checking. The
   documented "refuse to generate / BLOCKING banner on a superseded template" policy is therefore
   not enforced at generation time.

3. **Project access control is incomplete.** `_owned_project()` guards files, extractions,
   validation, documents, and audit. It is **not** applied in `projects.get_project`,
   `update_project`, `delete_project`, or `migrate_project`, so any authenticated user can read,
   modify, or delete another user's project if they know the id. `list_projects` does filter by
   owner for non-admins, which hides the gap from the UI but not from the API.

4. **`migrate_project` reports the wrong old version.** It assigns
   `project.template_version = template.version` and then reads `old_version` from the refreshed
   object, so `old_version` equals `new_version` in the response.

5. **Stale auto fields can survive a re-run.** Cleanup deletes and re-inserts only the fields the
   extractor returns. A field produced by an earlier run that the extractor no longer returns, and
   that was never confirmed, is left behind rather than removed.

`SPEC.md` records the original design intent; this folder describes the system as built.

---

## Versioning and status

**Project status** (`projects.status`): `draft` → `processing` → `review` → `validated` →
`generated`. Migration resets it to `draft`.

**Field status** (`extracted_fields.status`): `auto`, `confirmed`, `edited`, `missing`, `na`.

**Template status** (`templates.status`): `draft`, `verified`, `active`, `superseded`,
`deprecated`. Publishing a template marks any previously `active` template with the same body and
name as `superseded`.

**Template pinning.** A project stores `template_version` at creation. Publishing a new template
version never changes an existing project's output; migration is an explicit API call that also
resets project status to `draft`.

---

## Deployment shape

The default configuration needs **no external services**: SQLite plus local disk. Storage and the
database both degrade gracefully — if S3/MinIO is unreachable, storage falls back to
`LOCAL_STORAGE_DIR`.

Background work defaults to FastAPI `BackgroundTasks`, which is adequate for a single node. For
durable, retryable jobs, point `REDIS_URL` at Redis and run `app/workers/rq_worker.py`; the same
`pipeline` functions are enqueued unchanged.

See [`OPERATIONS.md`](OPERATIONS.md) for configuration and [`DATA-MODEL.md`](DATA-MODEL.md) for the
schema.
