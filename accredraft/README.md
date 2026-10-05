# AccreditDraft

**The evidence-to-document step, and only that step.**

Institutions hold accreditation evidence (event details, photos, circulars, certificates,
attendance sheets) in scattered, inconsistent files. Staff manually find, re-type, and arrange
this into body-specific formats, and usually discover the gaps only at submission time.

AccreditDraft compiles that: messy files in, a validated Word document out.

> It does **not** judge whether evidence satisfies an accreditation criterion, does not compute
> NAAC/NBA metrics, and does not decide whether your institution deserves accreditation.
> It assembles and validates the document.

---

## The idea, for a technical reader with limited AI background

Think of it as a **compiler for accreditation documents**.

- The messy files are the **source code**.
- The accreditation template is the **grammar and type system**: it declares which fields must exist.
- The AI is only the **parser**: it reads messy files and fills typed fields, noting where each
  value came from.
- A normal **validator** (plain code, like a type-checker) reports missing or inconsistent fields.
- A human fixes them.
- A **code generator** turns clean data into a Word file.

The AI never decides what is required, never decides whether the document is complete, and never
invents a missing value. New accreditation bodies are just new grammar files.

---

## Quick start (zero setup)

Requires **Python 3.10** and **Node 18+**. No database, no Redis, no cloud account needed —
it defaults to SQLite and local disk storage.

```bat
:: 1) Backend  (creates .venv with Python 3.10, installs deps, serves on :8000)
cd accredraft\backend
run.bat
```

```bat
:: 2) Frontend (in a second terminal)
cd accredraft\frontend
run.bat
```

`run.bat` installs the npm dependencies and builds on first run, then serves on :3000.

Open <http://127.0.0.1:3000>.

A demo admin is seeded on first backend start:

```
admin@example.com / admin12345
```

and one curated template: **NAAC · Criterion 3 · Extension Event Report · v2025**.

API docs: <http://127.0.0.1:8000/docs>

### Background processes instead of two terminals

```bat
cd accredraft\backend
.venv\Scripts\python.exe scripts\start_server.py      :: logs to backend\server.log

cd accredraft\frontend
python scripts\start_web.py                           :: logs to frontend\web.log
```

---

## The workflow

1. **Create a project** and pick a template. The project is **pinned** to that template version.
2. **Upload evidence** (PDF, DOCX, JPG/PNG, XLSX) — or fill fields by hand.
3. **Process** — files are parsed asynchronously into evidence items (text/table/image, with page
   and position). Scanned PDF pages fall back to OCR.
4. **Extraction review** — every field shows its value, a confidence score, and links to the exact
   source snippet. Confirm, edit, or mark *N/A*.
5. **Validation** — a checklist of OK / ERROR / WARNING, evaluated in code, never by the model.
6. **Generate** — render to DOCX (and PDF) through the layout template.

---

## Design rules

The rules the design is built around, and where each one lives. The **Status** column is honest
about what the code actually enforces today; the gaps are listed in full in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#where-the-implementation-is-narrower-than-the-intent).

| Rule | Where it lives | Status |
|---|---|---|
| Extraction and drafting are separate; facts are confirmed before any prose | review step before generation | enforced |
| A missing value is `null` — "not found" is a valid answer | `extractor.py`, schema-constrained output | enforced |
| The LLM never decides completeness; the validator does | `services/validator.py` (pure code) | enforced |
| Every extracted value carries provenance | `field_sources` table | LLM mode only — the keyword fallback emits none |
| Missing values render as a visible `[TO BE PROVIDED]` | `services/renderer.py` | enforced when the value is `null` |
| Template version is pinned per project | `projects.template_version` | enforced |
| Template version is stamped into the document | footer + document model | enforced |
| Every human edit is audited | `audit_log` table | enforced (`DELETE /files` is not logged) |
| Only confirmed values reach the document | `services/renderer.py` | **not enforced** — unreviewed and N/A values can render |
| Migration to a newer template version is an explicit action | `POST /projects/{id}/migrate` | **not reachable** — the lookup query can never match |

### Template resolution

```text
active + verified template exists?  -> use it
else latest verified superseded one -> use it + BLOCKING banner ("review before submission")
else                                -> refuse to generate
```

Only the first line is implemented, and only at project creation: `POST /api/projects` refuses a
template whose status is not `active`/`verified`. Generation does not re-check the template, so the
banner and refusal paths do not exist today.

Version pinning does hold: a project stores `template_version` at creation, and publishing a new
template version never changes an existing project's output.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | layers, module map, data flow per stage, the Document Model, design rules → code, and the known gaps |
| [`docs/DATA-MODEL.md`](docs/DATA-MODEL.md) | all 13 tables, status values, delete/cascade behaviour |
| [`docs/API.md`](docs/API.md) | every endpoint: auth, request, response, errors, and test coverage |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | configuration, running, optional infrastructure, troubleshooting, production checklist |
| [`SPEC.md`](SPEC.md) | the original design intent |

Interactive API docs are served at <http://127.0.0.1:8000/docs> when the API is running.

---

## Architecture

```
Next.js UI
   │  REST (proxied /api/*)
FastAPI  (auth, projects, templates, review APIs)
   │
Pipeline (FastAPI BackgroundTasks by default, RQ + Redis optional)
   ├─ ingestion  → parse / OCR / image classification
   ├─ extraction → LLM → structured fields + provenance
   ├─ validation → rules from the template schema (pure code)
   └─ render     → DOCX builder → LibreOffice → PDF
   │
SQLAlchemy → SQLite (default) or PostgreSQL   +   local disk or S3/MinIO
```

The key design choice is a **canonical Document Model (JSON)**, independent of any output format.
DOCX and PDF are just renderers of it.

### Two layers per template — never mixed

**A. Requirement schema** (`templates.schema_json`) — *what must be provided*. Drives both
extraction and validation: sections of typed fields, with `required` flags, plus a list of
validation rules.

**B. Layout template** — *how it looks*: a real `.docx` master with styles, filled by `docxtpl`.
Creating layout from scratch is far less reliable than filling a human-made master, so the layout
master is the primary path and the from-scratch renderer is the fallback.

The rule language is deliberately tiny (comparisons, dates, collection length). It must not grow
into a programming language.

Full schema examples and the module-by-module map are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Verification

One command runs everything — it starts the API in-process, starts the web app, runs all three
suites, then shuts both down:

```bat
cd accredraft
backend\.venv\Scripts\python.exe verify.py
```

Or run the suites individually against already-running servers:

```bat
cd accredraft\backend
.venv\Scripts\python.exe tests\test_e2e.py           :: 31 checks, full workflow + API surface
.venv\Scripts\python.exe tests\test_docx_output.py   :: 9 checks, document fidelity
```

```bat
cd accredraft\frontend
python tests\verify_stack.py    :: 10 checks: pages + /api proxy + an authorized call
```

Current status: **31/31**, **9/9**, **10/10** passing.

### If something fails with "connection refused" or a reset mid-request

On Windows two processes can bind the same port, and a leftover server from an earlier run will
split incoming connections between them. Stop the strays and retry:

```bat
cd accredraft
backend\.venv\Scripts\python.exe stop.py
```


---

## Configuration

`backend/.env` (copy from `backend/.env.example`):

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./accredraft.db` or a PostgreSQL URL | SQLite |
| `REDIS_URL` | only used by the optional RQ worker | `redis://localhost:6379/0` |
| `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` | object storage; falls back to `LOCAL_STORAGE_DIR` if unreachable | local disk |
| `OPENAI_API_KEY` | leave blank to use the deterministic keyword extractor | blank |
| `LLM_MODEL` | model used for extraction | `gpt-4o-mini` |
| `SECRET_KEY` | JWT signing — **change in production** | dev value |

**PDF output** needs LibreOffice on `PATH`. Without it, DOCX is still generated and the API
reports `pdf_available: false` instead of failing.

**OCR** needs the Tesseract binary on `PATH`. Without it, text-layer PDFs and DOCX still work.

**Privacy:** with `OPENAI_API_KEY` set, evidence text leaves your machine. Check your institution's
data policy before enabling it. Leaving the key blank keeps everything local.

---

## Going to PostgreSQL / Redis / MinIO

```bat
docker compose up -d
```

Then set `DATABASE_URL`, `REDIS_URL`, and `S3_*` in `backend/.env`, and install the Postgres driver:

```bat
cd accredraft\backend
.venv\Scripts\python.exe -m pip install -r requirements-postgres.txt
```

For durable, retryable jobs, run the worker:

```bat
.venv\Scripts\python.exe -m app.workers.rq_worker
```

---

## Scope

### In v1
- One body, one document type, one curated template
- Multi-file upload; text-layer PDF + DOCX parsing; OCR fallback for printed scans
- LLM extraction to ~10 fields with provenance
- Validation: required fields, date sanity, photo count, participant count
- Review/correction UI with per-field source snippets
- DOCX via a layout master + PDF via LibreOffice
- Template registry with status/version and explicit migration
- Audit log of every edit

### Deliberately out of v1
LaTeX export · cloning an arbitrary reference layout · multiple accreditation bodies ·
automatic template updates · handwriting OCR · auto-computed NAAC/NBA metrics ·
whole-SSR generation · multi-LLM routing · local models · real-time collaboration

---

## Honest limitations

- **Template curation is the bottleneck.** Schemas must be hand-written by a human reading the
  official documents. No AI will reliably turn a 200-page manual into a correct schema. Budget
  real time for this and expect it to be ongoing maintenance.
- **"Verified" means a human signed off** — not that a scraper or an AI checked it. Nothing is
  auto-scraped from accreditation websites in v1; an admin uploads the new official document and
  publishes a new version.
- **DOCX fidelity is the second-hardest part**: tables across pages, image sizing, captions, and
  TOC/page-number fields. python-docx cannot natively produce TOC/page-number/caption fields, so
  field-code XML is written by hand (see `renderer.add_page_numbers`).
- **Inferring layout from an arbitrary reference PDF is lossy** and is not promised.
- **The model can tell a certificate from a poster but cannot judge whether evidence is adequate.**
  Such soft judgements are WARNING-only, never pass/fail.
- **Conflicting values across documents are surfaced, not resolved.** The poster says 15 Sept, the
  report says 16 Sept — the reviewer decides.
- **Evaluation needs a labelled set.** Track per-field accuracy against 30–50 real events and rerun
  on every prompt or model change, or you will not know whether a change helped.
- **PDF output is untested here.** It needs LibreOffice, which is not installed in this environment,
  so the conversion path has never actually run.

### Known defects

Found while writing the documentation, verified by reading the code, and not yet fixed. Each is
described with its fix in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#where-the-implementation-is-narrower-than-the-intent).

1. **`POST /api/templates` always returns 422** — a Pydantic body model mixed with an `UploadFile`
   makes the model unparseable. There is no working way to create a template through the API, which
   matters because template curation is this product's acknowledged bottleneck.
2. **`POST /api/projects/{id}/migrate` can never succeed** — its lookup pins `Template.id` to the
   current row and then requires a greater `version`, which is unsatisfiable.
3. **Unconfirmed values reach the document** — the renderer prints any non-null value whose status
   is not `missing`, so `auto` (never reviewed) and `na` fields can render as if confirmed.
4. **Project access control is incomplete** — `GET/PUT/DELETE/migrate` on a project do not check
   ownership, so any authenticated user can act on another user's project given its id.
5. **Stale auto fields can survive a re-run** of extraction.

Test coverage, and the endpoints that have none, is listed in
[`docs/API.md`](docs/API.md#endpoint-coverage-in-tests).

Full design notes: [`SPEC.md`](SPEC.md).
