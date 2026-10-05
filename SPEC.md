# Accreditation Evidence to Document Platform - Specification

## 1. Project Overview

**Project Name:** AccreditDraft
**Type:** Full-stack web application (Next.js + FastAPI)
**Core Functionality:** Parse institutional accreditation evidence files, extract structured data using AI, validate against accreditation templates, and generate formatted DOCX/PDF documents.
**Target Users:** Institutional staff responsible for compiling accreditation submissions (NAAC, NBA, NEC).

---

## 2. Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐
│   Next.js UI    │────▶│  FastAPI REST   │
│  (Frontend)     │◀────│   (Backend)     │
└─────────────────┘     └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼─────┐ ┌────▼────┐ ┌────▼─────┐
              │ PostgreSQL│ │  Redis  │ │    S3    │
              │  (DB)     │ │ (Queue) │ │(Storage) │
              └───────────┘ └─────────┘ └──────────┘
```

### Tech Stack
- **Frontend:** Next.js 14 + Tailwind CSS + TypeScript
- **Backend:** FastAPI + Pydantic + SQLAlchemy
- **Queue:** RQ (Redis Queue) + Redis
- **Database:** PostgreSQL 15
- **Storage:** S3-compatible (MinIO for local dev)
- **DOCX Generation:** python-docx + docxtpl
- **PDF Conversion:** LibreOffice headless
- **OCR:** Tesseract (pytesseract)

---

## 3. Database Schema

### Tables

```sql
-- Organizations
organizations (
  id UUID PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
)

-- Users
users (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  email VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255),
  role VARCHAR(50) DEFAULT 'editor',
  password_hash VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW()
)

-- Templates
templates (
  id UUID PRIMARY KEY,
  body VARCHAR(100) NOT NULL,
  category VARCHAR(100) NOT NULL,
  name VARCHAR(255) NOT NULL,
  version VARCHAR(20) NOT NULL,
  status VARCHAR(20) DEFAULT 'draft',
  source_url TEXT,
  date_retrieved DATE,
  last_verified DATE,
  verified_by UUID REFERENCES users(id),
  valid_from DATE,
  valid_to DATE,
  schema_json JSONB NOT NULL,
  layout_file_id UUID,
  doc_hash VARCHAR(64),
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
)

-- Projects
projects (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  template_id UUID REFERENCES templates(id),
  template_version VARCHAR(20) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  status VARCHAR(50) DEFAULT 'draft',
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
)

-- Files (uploaded evidence)
files (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id),
  storage_key VARCHAR(500) NOT NULL,
  filename VARCHAR(255) NOT NULL,
  mime VARCHAR(100) NOT NULL,
  sha256 VARCHAR(64),
  page_count INTEGER,
  file_kind VARCHAR(50),
  created_at TIMESTAMP DEFAULT NOW()
)

-- Evidence Items (parsed content)
evidence_items (
  id UUID PRIMARY KEY,
  file_id UUID REFERENCES files(id),
  page INTEGER,
  bbox JSONB,
  item_type VARCHAR(50) NOT NULL,
  raw_text TEXT,
  ocr_confidence FLOAT,
  image_caption TEXT,
  classification VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW()
)

-- Extracted Fields
extracted_fields (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id),
  section_id VARCHAR(100) NOT NULL,
  field_id VARCHAR(100) NOT NULL,
  value_json JSONB,
  confidence FLOAT,
  status VARCHAR(50) DEFAULT 'auto',
  edited_by UUID REFERENCES users(id),
  edited_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
)

-- Field Sources (provenance)
field_sources (
  id UUID PRIMARY KEY,
  extracted_field_id UUID REFERENCES extracted_fields(id),
  evidence_item_id UUID REFERENCES evidence_items(id),
  snippet TEXT,
  created_at TIMESTAMP DEFAULT NOW()
)

-- Validation Runs
validation_runs (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id),
  template_version VARCHAR(20) NOT NULL,
  run_at TIMESTAMP DEFAULT NOW()
)

-- Validation Results
validation_results (
  id UUID PRIMARY KEY,
  run_id UUID REFERENCES validation_runs(id),
  rule_id VARCHAR(100) NOT NULL,
  field_id VARCHAR(100),
  status VARCHAR(20) NOT NULL,
  message TEXT,
  details JSONB
)

-- Documents (canonical model)
documents (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id),
  doc_model_json JSONB NOT NULL,
  version INTEGER DEFAULT 1,
  created_at TIMESTAMP DEFAULT NOW()
)

-- Generated Outputs
generated_outputs (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id),
  format VARCHAR(20) NOT NULL,
  storage_key VARCHAR(500) NOT NULL,
  template_version VARCHAR(20) NOT NULL,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMP DEFAULT NOW()
)

-- Audit Log
audit_log (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  project_id UUID REFERENCES projects(id),
  action VARCHAR(100) NOT NULL,
  before JSONB,
  after JSONB,
  ts TIMESTAMP DEFAULT NOW()
)
```

---

## 4. Template Schema Format

### Requirement Schema (JSONB)
```json
{
  "template_id": "naac-c3-event-report",
  "body": "NAAC",
  "version": "2025",
  "sections": [
    {
      "id": "event_basic",
      "title": "Event Details",
      "fields": [
        {"id": "title", "type": "string", "required": true, "label": "Event Title"},
        {"id": "date", "type": "date", "required": true, "label": "Event Date"},
        {"id": "venue", "type": "string", "required": true, "label": "Venue"},
        {"id": "organizer", "type": "string", "required": true, "label": "Organizing Department"},
        {"id": "objectives", "type": "text", "required": true, "min_items": 1, "label": "Objectives"},
        {"id": "participant_count", "type": "integer", "required": true, "label": "Total Participants"}
      ]
    },
    {
      "id": "evidence",
      "title": "Supporting Evidence",
      "fields": [
        {"id": "photos", "type": "image[]", "required": true, "min": 2, "label": "Event Photos", "caption_required": true},
        {"id": "attendance", "type": "file", "required": true, "label": "Attendance Sheet"}
      ]
    },
    {
      "id": "outcomes",
      "title": "Outcomes",
      "fields": [
        {"id": "description", "type": "text", "required": false, "label": "Event Description"}
      ]
    }
  ],
  "validation_rules": [
    {"id": "r1", "rule": "date <= today", "severity": "error", "message": "Event date cannot be in the future"},
    {"id": "r2", "rule": "participant_count >= 0", "severity": "error", "message": "Participant count must be non-negative"},
    {"id": "r3", "rule": "photos.length >= 2", "severity": "error", "message": "At least 2 photos required"}
  ]
}
```

### Document Model (Canonical)
```json
{
  "template_id": "naac-c3-event-report",
  "template_version": "2025",
  "generated_at": "2025-01-15T10:30:00Z",
  "sections": [
    {
      "id": "event_basic",
      "title": "Event Details",
      "fields": {
        "title": {"value": "Workshop on AI Ethics", "status": "confirmed", "sources": ["file_id", "evidence_item_id"]},
        "date": {"value": "2024-12-15", "status": "confirmed", "sources": ["file_id"]},
        "venue": {"value": "Main Auditorium", "status": "edited", "sources": [], "edited_value": "Conference Hall A"},
        "organizer": {"value": "Computer Science Department", "status": "confirmed", "sources": []},
        "objectives": {"value": ["Understand AI ethics principles", "Apply ethics in practice"], "status": "confirmed", "sources": []},
        "participant_count": {"value": 45, "status": "confirmed", "sources": []}
      }
    }
  ]
}
```

---

## 5. API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get JWT token
- `GET /api/auth/me` - Get current user

### Templates
- `GET /api/templates` - List templates (filter by body, status)
- `GET /api/templates/{id}` - Get template details
- `POST /api/templates` - Create template (admin)
- `PUT /api/templates/{id}` - Update template (admin)
- `GET /api/templates/{id}/layout` - Download layout template

### Projects
- `GET /api/projects` - List user's projects
- `POST /api/projects` - Create project
- `GET /api/projects/{id}` - Get project details
- `PUT /api/projects/{id}` - Update project
- `DELETE /api/projects/{id}` - Delete project
- `POST /api/projects/{id}/migrate` - Migrate to new template version

### Files
- `POST /api/projects/{id}/files` - Upload files
- `GET /api/projects/{id}/files` - List project files
- `DELETE /api/files/{id}` - Delete file
- `GET /api/files/{id}/evidence` - Get parsed evidence items

### Extraction & Review
- `POST /api/projects/{id}/extract` - Trigger extraction (async)
- `GET /api/projects/{id}/extractions` - Get extracted fields
- `PUT /api/projects/{id}/extractions/{field_id}` - Update extracted field
- `POST /api/projects/{id}/extractions/bulk` - Bulk confirm fields

### Validation
- `POST /api/projects/{id}/validate` - Run validation
- `GET /api/projects/{id}/validation` - Get validation results

### Document Generation
- `POST /api/projects/{id}/generate` - Generate DOCX (async)
- `GET /api/projects/{id}/documents` - List generated documents
- `GET /api/documents/{id}/download` - Download document

### WebSocket Events
- `processing_progress` - Job progress updates
- `extraction_complete` - Extraction finished
- `validation_complete` - Validation finished
- `generation_complete` - Document generated

---

## 6. User Workflow

### Step 1: Create Project
1. User selects organization
2. User selects template (e.g., "NAAC - Criterion 3 - Extension Event Report - v2025")
3. System creates project pinned to selected template version
4. Project shows template version in header

### Step 2: Upload Evidence
1. User uploads multiple files (PDF, DOCX, JPG, PNG, XLSX)
2. System accepts files up to 50MB each
3. Files appear in list with type icons
4. User can add manual form data alongside files

### Step 3: Process Files (Async)
1. User clicks "Process Files" or auto-triggers
2. Status changes to "Processing"
3. Progress shown via WebSocket (0-100%)
4. Workers handle:
   - PDF: PyMuPDF text extraction, fallback to OCR
   - DOCX: python-docx text/table extraction
   - Images: OCR + vision classification
   - XLSX: openpyxl table extraction

### Step 4: Extraction Review
1. System shows extracted fields organized by section
2. Each field shows:
   - Value extracted
   - Confidence score
   - Source links (file name, page, snippet)
   - Status badge (auto/confirmed/edited/missing/na)
3. User can:
   - Confirm field (click checkmark)
   - Edit field (click edit, modify, save)
   - Mark as not applicable (click N/A)
   - View source evidence (click link, modal shows snippet)

### Step 5: Validation
1. User clicks "Run Validation"
2. System runs all validation rules against confirmed fields
3. Results shown as checklist:
   - OK items (green)
   - ERROR items (red) - must fix
   - WARNING items (yellow) - review needed
4. Each result links to the relevant field
5. User fixes errors or explicitly acknowledges warnings

### Step 6: Preview & Generate
1. User clicks "Generate Document"
2. System renders DOCX from confirmed fields
3. Preview shown in-browser (or download)
4. MISSING fields show as "[TO BE PROVIDED]" highlighted
5. User downloads DOCX and edits in Word if needed
6. PDF available via LibreOffice conversion

---

## 7. Frontend Pages

### Dashboard (`/`)
- Project cards with status badges
- Recent activity feed
- Quick actions (new project)

### Project Detail (`/projects/{id}`)
- Header: Project name, template info, status
- Tabs: Files | Extracted Data | Validation | Document
- File upload dropzone
- Evidence list with type icons
- Extraction review table
- Validation checklist
- Generate button

### Template Registry (`/templates`)
- Admin-only template management
- Table: Name, Body, Version, Status, Last Verified
- Add/Edit template modal
- Upload layout template

### Admin Panel (`/admin`)
- User management
- Organization settings
- Audit log viewer

---

## 8. Layout Template System

### Master DOCX Structure
The layout template uses styles that map to sections:
- `Heading 1` - Section titles
- `Heading 2` - Field labels
- `Normal` - Field values
- `Caption` - Image captions
- `Table` - Structured data tables

### Field Mapping
```
{{title}} -> Event title value
{{date}} -> Formatted date
{{photo_1}} -> First evidence image
{{photo_2}} -> Second evidence image
{{missing_venue}} -> "[TO BE PROVIDED]" if not provided
```

---

## 9. Worker Jobs (RQ)

### `ingestion_worker`
- Download file from S3
- Detect file type
- Parse based on type (PDF/DOCX/Image/XLSX)
- Store evidence items in DB

### `extraction_worker`
- Fetch evidence items for project
- Build context from all evidence
- Call LLM with field schema
- Parse structured output
- Store extracted fields with source refs

### `validation_worker`
- Load project extractions
- Load template validation rules
- Execute each rule in code
- Store validation results

### `render_worker`
- Load document model
- Load layout template
- Fill template with confirmed fields
- Handle missing fields (placeholder text)
- Upload to S3
- Convert to PDF via LibreOffice

---

## 10. MVP Scope (v1)

### Included
- Single template: "NAAC - Criterion 3 - Extension Event Report - v2025"
- Multi-file upload (PDF, DOCX, JPG/PNG)
- Text-layer PDF and DOCX parsing
- Basic OCR on printed text
- LLM extraction to ~10 fields with source links
- Validation: required fields, date sanity, photo count
- Review/correction UI
- DOCX output with master template styling
- PDF output via LibreOffice
- Template registry with status/version
- Audit log

### Excluded (v1)
- LaTeX export
- Automatic template updates
- Multiple accreditation bodies
- Handwriting OCR
- Local models
- Real-time collaboration
- Template builder UI

---

## 11. Acceptance Criteria

### Functional
- [x] User can register and login
- [x] User can create project with template
- [x] User can upload multiple files (PDF, DOCX, images)
- [x] System parses files and shows evidence items
- [x] System extracts fields with confidence and sources
- [x] User can review and edit extracted fields
- [x] System validates fields against rules
- [x] User can generate DOCX from confirmed data
- [x] User can download DOCX and PDF
- [x] Template versioning prevents silent changes
- [x] All field changes are audited

### Non-Functional
- [x] Processing completes within 2 minutes for 10 files
- [x] Extracted values have provenance links
- [x] No hallucination: only confirmed values used in generation
- [x] Generated documents match layout template styling

---

## 12. Configuration

### Environment Variables
```
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/accredraft

# Redis
REDIS_URL=redis://localhost:6379/0

# S3 Storage
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=accredraft

# LLM (OpenAI)
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# App
SECRET_KEY=your-secret-key-here
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 13. Security

- JWT authentication for all API endpoints
- Role-based access (admin, editor, viewer)
- Organization-scoped data isolation
- Audit log for all changes
- File type validation (magic bytes, not just extension)
- Max file size limits enforced server-side