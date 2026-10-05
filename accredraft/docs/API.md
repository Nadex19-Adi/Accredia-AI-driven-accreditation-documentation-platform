# API reference

Base URL `http://127.0.0.1:8000`. Interactive docs at `/docs`.

Every endpoint below lives under `/api`. The Next.js frontend calls the same paths and proxies them
via `frontend/next.config.mjs`, so browser code never needs CORS.

---

## Authentication

JWT bearer tokens, signed HS256.

```
Authorization: Bearer <access_token>
```

| Situation | Response |
|---|---|
| No `Authorization` header, or not `Bearer …` | `403` (FastAPI `HTTPBearer`) |
| Invalid or expired token | `401 Could not validate credentials` |
| Valid token, endpoint is admin-only, user is not admin | `403 Admin access required` |

Tokens are issued by `POST /api/auth/login` and expire after
`ACCESS_TOKEN_EXPIRE_MINUTES` (default 7 days). Passwords are bcrypt-hashed.

Roles: `admin` and `editor`. Registration always creates an `editor`. Admins see all projects;
other users only see their own in list endpoints.

---

## Error format

Standard FastAPI shapes:

```json
{ "detail": "Project not found" }
```

```json
{ "detail": [ { "type": "missing", "loc": ["body", "name"], "msg": "Field required" } ] }
```

A string `detail` means a handled application error; an array means request validation (`422`).

---

## Meta

| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/` | none | app name, version, scope note |
| GET | `/api/health` | none | `{"status": "ok"}` |
| GET | `/docs` | none | Swagger UI |

---

## Auth

### `POST /api/auth/register` — no auth
Creates an `editor` user, and the organization if `org_name` is new.

```json
{ "email": "user@example.com", "password": "at-least-8-chars", "name": "Full Name",
  "org_name": "Optional Institution" }
```

Returns `UserResponse`. Errors: `400` email already registered, `422` password shorter than 8.

### `POST /api/auth/login` — no auth

```json
{ "email": "admin@example.com", "password": "admin12345" }
```

Returns `{"access_token": "…", "token_type": "bearer"}`. Errors: `401` wrong credentials,
`400` account deactivated.

### `GET /api/auth/me` — auth
Returns the current `UserResponse`.

---

## Templates

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/templates` | any | optional `?body=` and `?status=` filters |
| GET | `/api/templates/{template_id}` | any | `404` if missing |
| POST | `/api/templates` | **admin** | **currently unusable — see below** |
| PUT | `/api/templates/{template_id}` | **admin** | partial update |
| GET | `/api/templates/{template_id}/layout` | any | downloads the layout `.docx`, `404` if none |
| POST | `/api/templates/{template_id}/publish` | **admin** | `draft`/`verified` → `active` |

Non-admins only see templates whose status is `active` or `verified` in the **list** endpoint.
`GET /api/templates/{id}` has no such filter, so any authenticated user who knows an id can read a
`draft` template's schema.

**`PUT`** accepts any of: `name`, `status`, `last_verified`, `verified_by`, `valid_from`,
`valid_to`, `schema_json`, `layout_template_path`. Supplying `schema_json` here is the practical way
to change a template's requirements, since `POST` is broken.

**`POST /publish`** moves any `active` template with the same `body` and `name` to `superseded`,
then sets the target to `active` and stamps `last_verified` and `verified_by`. Errors: `400` unless
the current status is `draft` or `verified`, `404` if missing.

### Known defect: `POST /api/templates` always returns 422

The handler declares both a Pydantic body model and an `UploadFile`:

```python
def create_template(data: TemplateCreate, layout_file: UploadFile = File(None), ...)
```

The `File` parameter forces the request to be parsed as `multipart/form-data`, which makes FastAPI
look for the model under the form field `data`. Multipart values are always strings, so the nested
object can never be constructed. Every attempt observed during verification failed:

| Request | Result |
|---|---|
| `multipart/form-data` with model fields at top level | `422` `body.data` missing |
| `application/json` with model fields | `422` `body.data` missing |
| `application/json` with `{"data": {...}}` | `422` `body.data` missing |
| `multipart` with `data` as a JSON string | `422` `body.data` must be a dict |
| `multipart` with `data[body]`, `data[category]`, … | `422` `body.data` missing |

**Consequence:** there is no working way to create a template through the API. In practice the only
template that exists is the one seeded at startup. Since template curation is the acknowledged
bottleneck of this product, this is the highest-impact defect in the codebase. The fix is to either
accept the schema as a JSON string form field and parse it, or move the layout upload to a separate
endpoint.

---

## Projects

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/projects` | any | optional `?status=`, `?template_id=`; newest first |
| POST | `/api/projects` | any | creates and **pins** the template version |
| GET | `/api/projects/{project_id}` | any | `404` if missing |
| PUT | `/api/projects/{project_id}` | any | `name`, `description`, `status` |
| DELETE | `/api/projects/{project_id}` | any | cascades (see DATA-MODEL) |
| POST | `/api/projects/{project_id}/migrate` | any | **currently always 404 — see below** |

`GET /api/projects` filters to `created_by == current_user` for non-admins. The other five
endpoints do **not** check ownership, so any authenticated user can read, update, delete, or migrate
another user's project given its id.

**`POST`** body:

```json
{ "template_id": "uuid", "name": "Extension Event Report", "description": "optional" }
```

Errors: `404` template not found, `400` if the template status is not `active`/`verified`.
The response includes `template_version`, copied from the template at this moment.

### Known defect: `POST /api/projects/{id}/migrate` can never succeed

```python
template = db.query(Template).filter(
    Template.id == project.template_id,          # pins to the exact current row
    Template.version > project.template_version, # …then requires a greater version
    Template.status.in_(["active", "verified"]),
).order_by(Template.version).first()
```

A template row has exactly one `version`, so `id == current AND version > current` is
unsatisfiable. The endpoint always returns `404 No newer template version found`.

The query should select by `body` and `name` (the identity of a template across versions) rather
than by `id`. Separately, the success response reports `old_version` from the refreshed project
after it has already been assigned the new version, so `old_version` would equal `new_version` even
if the query worked.

Because of this, the documented "explicit migration to a newer template version" workflow is not
currently usable.

---

## Files

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/projects/{project_id}/files` | any | `multipart/form-data`, field name `files`, repeatable |
| GET | `/api/projects/{project_id}/files` | any | oldest first |
| DELETE | `/api/files/{file_id}` | any | deletes the row and the stored blob |
| GET | `/api/files/{file_id}/evidence` | any | parsed evidence items, ordered by page |
| GET | `/api/files/{file_id}/download` | any | streams the original upload |

Upload constraints: extension must be in `ALLOWED_EXTENSIONS`
(`.pdf .docx .doc .jpg .jpeg .png .xlsx .xls`) and size ≤ `MAX_FILE_SIZE` (50 MB). Violations return
`400`.

`file_kind` (`pdf`, `docx`, `image`, `xlsx`) is derived at upload and returned in the response.

`GET …/evidence` returns the parsed units — one row per text block, table, or image — each with
`page`, `bbox`, `item_type`, `raw_text`, `ocr_confidence`, `image_caption`, `classification`.

`DELETE` writes no audit entry, though the UI exposes the action.

---

## Pipeline triggers

Each `/sync` endpoint runs the stage inline and returns its result; the non-`/sync` counterparts
enqueue the same function via FastAPI `BackgroundTasks` and return immediately.

| Method | Path | Auth | Returns |
|---|---|---|---|
| POST | `/api/projects/{id}/process` | any | `{"message": "Processing started", "stage": "ingestion"}` |
| POST | `/api/projects/{id}/extract` | any | `{"message": "Extraction started", "stage": "extraction"}` |
| POST | `/api/projects/{id}/validate` | any | `{"message": "Validation started", "stage": "validation"}` |
| POST | `/api/projects/{id}/validate/sync` | any | `{"run_id", "ok", "errors", "warnings"}` |
| POST | `/api/projects/{id}/generate` | any | `{"message": "Generation started", "stage": "render"}` |
| POST | `/api/projects/{id}/generate/sync` | any | `{"document_id", "docx_key", "pdf_key", "pdf_available"}` |

`validate/sync` and `generate/sync` return `400` when the stage reports an error. The async variants
always return `200`, because the work has not happened yet — poll the corresponding `GET` endpoint.

`pdf_available` is `false` whenever LibreOffice is not on `PATH`; DOCX is still produced.

---

## Extraction review

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/projects/{project_id}/extractions` | any | full form, with sources and labels |
| PUT | `/api/projects/{project_id}/extractions/{field_id}` | any | confirm / edit / mark N/A |
| POST | `/api/projects/{project_id}/extractions/bulk` | any | set status on many fields |

`GET` returns one entry per schema field, even fields the extractor never mentioned (seeded as
`missing`), so the review UI always shows the complete form. Each entry carries `label` resolved
from the template schema and a `sources` array of `{id, evidence_item_id, snippet, file_name, page}`.

`PUT` body — both keys optional:

```json
{ "value": "Workshop on AI Ethics", "status": "edited" }
```

Rules as implemented:

- supplying `value` sets it and defaults `status` to `edited`
- supplying `status` alone changes only the status
- `status: "missing"` **also clears** the value to `null`
- `status: "na"` does **not** clear the value — see the renderer caveat in ARCHITECTURE
- every call stamps `edited_by` / `edited_at` and writes a `field.update` audit entry

The response echoes the updated field but with an **empty `sources` array**, unlike `GET`.

`POST …/bulk`:

```json
{ "field_ids": ["uuid", "uuid"], "status": "confirmed" }
```

Returns `{"message": "Updated N fields", "count": N}` and writes one `fields.bulk_status` audit
entry.

---

## Validation

### `GET /api/projects/{project_id}/validation`
Returns the most recent `ValidationRun` with its results sorted `error` → `warning` → `ok`.

```json
{ "id": "uuid", "project_id": "uuid", "template_version": "2025", "run_at": "…",
  "results": [ { "id": "uuid", "rule_id": "r1", "field_id": "date", "status": "error",
                 "message": "Event date cannot be in the future", "details": null } ] }
```

`404 No validation run yet` before the first run.

---

## Documents

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/projects/{project_id}/documents` | any | Document Models, newest version first |
| GET | `/api/projects/{project_id}/outputs` | any | rendered files, newest first |
| GET | `/api/outputs/{output_id}/download` | any | streams DOCX or PDF |

`documents.doc_model_json` is the canonical Document Model the renderers consume — useful for
debugging what actually reached the output.

Download sets `Content-Disposition: attachment; filename="report_v{version}.{format}"` and writes an
`output.download` audit entry. `404` if the record is missing or the blob cannot be read.

---

## Audit

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/projects/{project_id}/audit` | any | optional `?limit=` (default 100), newest first |
| GET | `/api/audit` | **admin only** | global log, `403` for non-admins |

Entries carry `action`, `before`, `after`, and `ts`. Actions written today: `user.register`,
`project.create`, `project.update`, `project.delete`, `project.migrate`, `files.upload`,
`field.update`, `fields.bulk_status`, `output.download`.

---

## Endpoint coverage in tests

`backend/tests/test_e2e.py` exercises every endpoint the frontend calls, plus the delete paths:
login → templates → project → upload → process → extract → review edit → mark N/A → validate →
generate → download → audit → `/auth/me` → `/templates/{id}` → `/validation` → `/documents` →
delete file → delete project → confirm `404`.

Not covered by any test, and therefore unverified: `POST /api/auth/register`, `PUT /api/projects/{id}`,
`POST /api/projects/{id}/migrate`, `PUT /api/templates/{id}`, `POST /api/templates`,
`POST /api/templates/{id}/publish`, `GET /api/files/{id}/download`, `GET /api/templates/{id}/layout`,
`GET /api/audit`, and the three asynchronous (non-`/sync`) pipeline triggers.
