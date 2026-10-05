# Operations

Running, configuring, testing, and troubleshooting AccreditDraft.

---

## Requirements

| Component | Version | Notes |
|---|---|---|
| Python | 3.10 | the launcher scripts use `py -3.10` |
| Node.js | 18 or newer | tested on 24 |
| LibreOffice | optional | enables PDF output |
| Tesseract | optional | enables OCR for scanned PDFs |

No database, queue, or cloud account is needed. The defaults are SQLite plus local disk.

---

## Running it

### Two terminals (recommended)

```bat
cd accredraft\backend
run.bat
```

```bat
cd accredraft\frontend
run.bat
```

`backend\run.bat` creates `.venv` with Python 3.10, installs requirements, and serves the API on
`:8000` with `--reload`. `frontend\run.bat` installs npm dependencies and builds on first run, then
serves on `:3000`.

Open <http://127.0.0.1:3000>. The seeded admin is `admin@example.com` / `admin12345`.

### Background processes

```bat
cd accredraft\backend
.venv\Scripts\python.exe scripts\start_server.py     :: API, waits for /api/health
.venv\Scripts\python.exe scripts\start_server.py --reload

cd accredraft\frontend
python scripts\start_web.py                          :: production build
python scripts\start_web.py --dev                    :: dev server
```

Both are idempotent — if the service is already answering, they exit successfully. Logs go to
`backend\server.log` and `frontend\web.log`.

### Stopping

```bat
cd accredraft
backend\.venv\Scripts\python.exe stop.py
```

Stops whatever is listening on `:8000` and `:3000`. Use this if you see connection resets: on
Windows two processes can bind the same port, and a leftover server will split incoming connections
between them.

### Resetting local state

```bat
cd accredraft\backend
del accredraft.db
rmdir /s /q storage
```

The database and storage are recreated on next start, along with the demo admin and the NAAC
template.

---

## Configuration

Settings live in `backend/.env` (copy `backend/.env.example`). Defaults are chosen so the stack runs
untouched.

| Variable | Purpose | Default |
|---|---|---|
| `APP_NAME` | shown in the API root and docs | `AccreditDraft` |
| `DEBUG` | debug flag | `true` |
| `SECRET_KEY` | JWT signing key — **change in production** | dev placeholder |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///./accredraft.db` |
| `REDIS_URL` | only used by the optional RQ worker | `redis://localhost:6379/0` |
| `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` / `S3_REGION` | object storage | MinIO defaults on `localhost:9000` |
| `LOCAL_STORAGE_DIR` | fallback storage root | `storage` |
| `OPENAI_API_KEY` | **blank uses the deterministic keyword extractor** | blank |
| `LLM_MODEL` | model for extraction | `gpt-4o-mini` |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | token lifetime | `10080` (7 days) |
| `MAX_FILE_SIZE` | upload limit in bytes | `52428800` (50 MB) |
| `ALLOWED_EXTENSIONS` | accepted upload extensions | `.pdf .docx .doc .jpg .jpeg .png .xlsx .xls` |
| `LAYOUT_TEMPLATES_DIR` | where uploaded layout masters are stored | `templates` |

### The `OPENAI_API_KEY` switch

With the key **blank** (the default) extraction uses a deterministic regex/keyword extractor. It is
weaker but entirely local, and it is what the test suite runs against.

Two consequences worth understanding:

- The fallback **emits no provenance**. `field_sources` stays empty, so the review UI shows no
  source snippets. Provenance is a feature of LLM mode only.
- With a key set, **evidence text leaves your machine**. Check your institution's data policy first.

---

## Optional infrastructure

```bat
docker compose up -d
```

Starts PostgreSQL, Redis, and MinIO. Then point `backend/.env` at them:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/accredraft
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=http://localhost:9000
```

PostgreSQL needs its driver:

```bat
cd accredraft\backend
.venv\Scripts\python.exe -m pip install -r requirements-postgres.txt
```

For durable, retryable jobs instead of in-process `BackgroundTasks`:

```bat
.venv\Scripts\python.exe -m app.workers.rq_worker
```

The same `pipeline` functions are enqueued unchanged.

---

## Testing

One command runs everything — it starts the API in-process, starts the web app, runs all three
suites, then shuts both down:

```bat
cd accredraft
backend\.venv\Scripts\python.exe verify.py
```

`verify.py` stops stale listeners on the app ports before starting, so it is safe to run repeatedly.
Exit code is 0 only when every suite passes.

Individually, against already-running servers:

```bat
cd accredraft\backend
.venv\Scripts\python.exe tests\test_e2e.py           :: 31 checks
.venv\Scripts\python.exe tests\test_docx_output.py   :: 9 checks

cd accredraft\frontend
python tests\verify_stack.py                         :: 10 checks
```

| Suite | What it proves |
|---|---|
| `test_e2e.py` | full workflow: login → template → project → upload → ingest → extract → review edit → mark N/A → validate → generate → download → audit, then the API surface the frontend depends on, then cleanup and `404` |
| `test_docx_output.py` | document fidelity: confirmed values render, missing values become `[TO BE PROVIDED]`, template id + version in the footer, no placeholder leakage |
| `verify_stack.py` | pages render real markup, the `/api` proxy works, an authorized call succeeds through it |

Current status: **31/31**, **9/9**, **10/10**.

Endpoints with no test coverage are listed at the end of [`API.md`](API.md#endpoint-coverage-in-tests).

---

## Troubleshooting

### Connection refused, or a reset partway through a request

Almost always a duplicate port binding. Windows permits two processes to bind the same port, and
the OS then distributes connections between them; when one dies, in-flight requests fail.

```bat
cd accredraft
backend\.venv\Scripts\python.exe stop.py
```

Then start a single instance.

### `next build` fails: "not a valid Win32 application"

The SWC native binary (`node_modules/@next/swc-win32-x64-msvc/*.node`) is truncated or corrupt —
usually a download that was cut short behind a proxy. Next.js 14 requires this binary; the Babel
fallback is not sufficient because Next still loads SWC.

```bat
cd accredraft\frontend
rmdir /s /q node_modules\@next\swc-win32-x64-msvc
npm install @next/swc-win32-x64-msvc@14.2.5 --no-audit --no-fund --force
```

Sanity check the result — a healthy binary is roughly 130 MB and loads cleanly:

```bat
node -e "require('./node_modules/@next/swc-win32-x64-msvc/next-swc.win32-x64-msvc.node');console.log('ok')"
```

### PDF is missing from the outputs

LibreOffice is not on `PATH`. The API reports `"pdf_available": false` and still produces the DOCX —
this is designed degradation, not a failure. Install LibreOffice and restart the API.

Note that **the PDF path has never been exercised in this environment**, since LibreOffice is not
installed here. Treat PDF output as untested until you run it yourself.

### Scanned PDFs yield no text

Tesseract is not on `PATH`. Text-layer PDFs and DOCX files are unaffected. Handwriting is out of
scope entirely.

### A field is missing from the review screen

Extraction seeds every field declared in the template schema, so a gap means the field is absent
from `schema_json` — not that the extractor failed.

### Extraction returns nothing

Check that files were processed first: ingestion (`/process`) must run before extraction
(`/extract`), because extraction reads `evidence_items`. In the UI, use *Evidence → Process*, then
*Extraction review → Run extraction*.

### Tests fail only when run right after a previous run

Stale listeners again — `stop.py`, then re-run. `verify.py` handles this itself.

---

## Production checklist

Before exposing this beyond a single machine:

1. **Set `SECRET_KEY`** to a long random value. The default signs tokens that anyone can forge.
2. **Set a real password** for the admin account, or delete the seeded demo user.
3. **Move to PostgreSQL** and run the RQ worker so jobs survive a restart.
4. **Put storage on S3/MinIO**, or back up `LOCAL_STORAGE_DIR`.
5. **Terminate TLS** in front of the API; tokens are bearer tokens over plain HTTP otherwise.
6. **Reconsider `--reload`** — it is a development convenience.
7. **Decide on `OPENAI_API_KEY`** deliberately, per your institution's data policy.
8. **Review the access-control gaps** in [`ARCHITECTURE.md`](ARCHITECTURE.md#where-the-implementation-is-narrower-than-the-intent).
   In particular, project endpoints other than `GET /api/projects` do not verify ownership.

---

## Honest limitations

- **Template curation is the bottleneck.** Schemas must be hand-written by a human reading the
  official documents. No model reliably turns a 200-page manual into a correct schema. Budget real
  time for this, and note that `POST /api/templates` is currently broken, so today schemas can only
  be changed via `PUT`.
- **"Verified" means a human signed off** — not that a scraper or a model checked it. Nothing is
  auto-scraped in v1.
- **DOCX fidelity is the second-hardest part**: tables that span pages, image sizing, captions, TOC
  and page-number fields. `python-docx` cannot natively emit TOC or page-number fields, so the field
  XML is written by hand in `renderer.add_page_numbers`.
- **Inferring layout from an arbitrary reference PDF is lossy** and is not promised.
- **The model can tell a certificate from a poster but cannot judge whether evidence is adequate.**
  Such judgements are WARNING-only, never pass/fail.
- **Conflicting values across documents are surfaced, not resolved.** The poster says 15 Sept, the
  report says 16 Sept — the reviewer decides.
- **Evaluation needs a labelled set.** Track per-field accuracy against 30–50 real events and re-run
  on every prompt or model change, or you will not know whether a change helped.
- **The keyword fallback extractor is a demo path**, not a production one. It recognises a fixed
  vocabulary (`title`, `date`, `venue`, `organizer`, `participant_count`, `objectives`) and produces
  no provenance.

Design intent is in [`SPEC.md`](../SPEC.md); the system as built is described in this folder.
