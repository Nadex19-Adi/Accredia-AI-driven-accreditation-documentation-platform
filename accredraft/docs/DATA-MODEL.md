# Data model

13 tables, defined in `backend/app/models/models.py`. Portable across SQLite and PostgreSQL via the
`GUID` and `JSONType` helpers in `backend/app/models/types.py`.

---

## Entity relationships

```
organizations ─┬─< users ─────────────< audit_log
               └─< projects ─┬─< files ──< evidence_items ──< field_sources
                             ├─< extracted_fields ──< field_sources
                             ├─< validation_runs ──< validation_results
                             ├─< documents ──< generated_outputs
                             └─< audit_log

templates ──< projects            (projects pin a template + version)
```

---

## Tables

### `organizations`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `name` | string(255) | not null |
| `created_at` | datetime | |

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `org_id` | GUID | FK → `organizations.id`, nullable |
| `email` | string(255) | **unique**, not null, indexed |
| `name` | string(255) | |
| `role` | string(50) | default `editor`; values in use: `admin`, `editor` |
| `password_hash` | string(255) | bcrypt |
| `is_active` | bool | default true |
| `created_at` | datetime | |

`viewer` appears in the schema comment but is never assigned — `POST /api/auth/register` always
creates an `editor`.

### `templates`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `body` | string(100) | not null, indexed — `NAAC`, `NBA`, … |
| `category` | string(100) | not null |
| `name` | string(255) | not null |
| `version` | string(20) | not null |
| `status` | string(20) | indexed, default `draft` |
| `source_url` | text | where the official document came from |
| `date_retrieved` | date | |
| `last_verified` | date | set on publish |
| `verified_by` | GUID | FK → `users.id` |
| `valid_from` / `valid_to` | date | informational |
| `schema_json` | JSON | **not null** — the requirement schema |
| `layout_template_path` | string(500) | path to the layout `.docx` |
| `doc_hash` | string(64) | |
| `created_by` | GUID | FK → `users.id` |
| `created_at` / `updated_at` | datetime | |

Uniqueness of `(body, name, version)` is checked in `api/templates.py`, **not** by a DB constraint
(the `__table_args__` is empty).

### `projects`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `org_id` | GUID | FK → `organizations.id` |
| `template_id` | GUID | FK → `templates.id` |
| `template_version` | string(20) | **not null — pinned at creation** |
| `name` | string(255) | not null |
| `description` | text | |
| `status` | string(50) | indexed, default `draft` |
| `created_by` | GUID | FK → `users.id` |
| `created_at` / `updated_at` | datetime | |

### `files`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `project_id` | GUID | FK → `projects.id` |
| `storage_key` | string(500) | not null |
| `filename` | string(255) | not null |
| `mime` | string(100) | not null |
| `sha256` | string(64) | content hash at upload |
| `page_count` | int | set during ingestion |
| `file_kind` | string(50) | `pdf`, `docx`, `image`, `xlsx` |
| `created_at` | datetime | |

### `evidence_items`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `file_id` | GUID | FK → `files.id` |
| `page` | int | |
| `bbox` | JSON | `{x, y, width, height}` |
| `item_type` | string(50) | **not null** — `text`, `table`, `image` |
| `raw_text` | text | the parsed or OCR'd content |
| `ocr_confidence` | float | 0–1, scans only |
| `image_caption` | text | |
| `classification` | string(100) | `certificate`, `photo`, `poster`, `attendance_sheet` |
| `created_at` | datetime | |

### `extracted_fields`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `project_id` | GUID | FK → `projects.id` |
| `section_id` | string(100) | not null — matches a section in the schema |
| `field_id` | string(100) | not null — matches a field in that section |
| `value_json` | JSON | the value; `NULL` means "not found" |
| `confidence` | float | 0–1 |
| `status` | string(50) | default `auto` |
| `edited_by` | GUID | FK → `users.id` |
| `edited_at` | datetime | |
| `created_at` | datetime | |

The `(project_id, section_id, field_id)` triple is intended to be unique, but that constraint is
**not** declared in the DB — the `__table_args__` is empty. Correctness relies on the application
deleting before inserting; concurrent extraction runs against the same project could create
duplicates.

### `field_sources` — provenance
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `extracted_field_id` | GUID | FK → `extracted_fields.id` |
| `evidence_item_id` | GUID | FK → `evidence_items.id` |
| `snippet` | text | the quoted source text, truncated to 2000 chars |
| `created_at` | datetime | |

One row per piece of evidence that supports a value. This is what the review UI shows when you
click *"N sources"*.

### `validation_runs`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `project_id` | GUID | FK → `projects.id` |
| `template_version` | string(20) | not null — the version the rules came from |
| `run_at` | datetime | |

### `validation_results`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `run_id` | GUID | FK → `validation_runs.id` |
| `rule_id` | string(100) | not null |
| `field_id` | string(100) | nullable — rule may be document-wide |
| `status` | string(20) | not null — `ok`, `error`, `warning` |
| `message` | text | |
| `details` | JSON | structured context |

### `documents`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `project_id` | GUID | FK → `projects.id` |
| `doc_model_json` | JSON | **not null** — the canonical Document Model |
| `version` | int | default 1, increments per generation |
| `created_at` | datetime | |

### `generated_outputs`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `document_id` | GUID | FK → `documents.id` |
| `format` | string(20) | not null — `docx`, `pdf` |
| `storage_key` | string(500) | not null |
| `template_version` | string(20) | not null |
| `created_by` | GUID | FK → `users.id` |
| `created_at` | datetime | |

One row per rendered file. A single generation normally produces one `docx` row and, when
LibreOffice is present, one `pdf` row.

### `audit_log`
| Column | Type | Notes |
|---|---|---|
| `id` | GUID | PK |
| `user_id` | GUID | FK → `users.id` |
| `project_id` | GUID | FK → `projects.id` |
| `action` | string(100) | not null |
| `before` | JSON | prior state |
| `after` | JSON | new state |
| `ts` | datetime | |

Actions recorded today: `user.register`, `project.create`, `project.update`, `project.delete`,
`project.migrate`, `files.upload`, `file.delete`\*, `field.update`, `fields.bulk_status`,
`output.download`.

\* `DELETE /api/files/{id}` does not write an audit entry, even though the frontend exposes the
action.

---

## Status values

| Entity | Column | Values |
|---|---|---|
| Project | `projects.status` | `draft`, `processing`, `review`, `validated`, `generated` |
| Field | `extracted_fields.status` | `auto`, `confirmed`, `edited`, `missing`, `na` |
| Template | `templates.status` | `draft`, `verified`, `active`, `superseded`, `deprecated` |
| Validation | `validation_results.status` | `ok`, `error`, `warning` |

---

## Delete behaviour

| Deleting | Cascades to | Notes |
|---|---|---|
| `projects` | `files` → `evidence_items` → `field_sources`; `extracted_fields`; `documents` → `generated_outputs`; `validation_runs` → `validation_results` | declared `cascade="all, delete-orphan"` |
| `files` | `evidence_items` | |
| `extracted_fields` | `field_sources` | |
| `validation_runs` | `validation_results` | |
| `documents` | `generated_outputs` | |
| `templates` | — | referenced by `projects.template_id`; there is no delete endpoint for templates |

`audit_log` is deliberately **not** cascaded from `projects`. Deleting a project nullifies the
audit rows' `project_id` rather than removing them, so the trail survives the deletion — which is
the desired behaviour for an audit log, though it means a deleted project's history is only
reachable through the global `GET /api/audit` admin endpoint.

Storage objects are **not** deleted when a project is deleted; only a single file's blob is removed
by `DELETE /api/files/{id}`.
