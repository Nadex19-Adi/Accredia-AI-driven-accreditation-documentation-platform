"""AccreditDraft API application entrypoint."""
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, SessionLocal
from app.api import auth, templates, projects, files, extractions, validation, documents, audit

NAAC_SCHEMA = {
    "template_id": "naac-c3-event-report",
    "body": "NAAC",
    "version": "2025",
    "sections": [
        {
            "id": "event_basic",
            "title": "Event Details",
            "fields": [
                {"id": "title", "type": "string", "required": True, "label": "Event Title"},
                {"id": "date", "type": "date", "required": True, "label": "Event Date"},
                {"id": "venue", "type": "string", "required": True, "label": "Venue"},
                {"id": "organizer", "type": "string", "required": True, "label": "Organizing Department"},
                {"id": "objectives", "type": "text[]", "required": True, "min_items": 1, "label": "Objectives"},
                {"id": "participant_count", "type": "integer", "required": True, "label": "Total Participants"},
            ],
        },
        {
            "id": "evidence",
            "title": "Supporting Evidence",
            "fields": [
                {"id": "photos", "type": "image[]", "required": True, "min": 2,
                 "caption_required": True, "label": "Event Photos"},
                {"id": "attendance", "type": "file", "required": True, "label": "Attendance Sheet"},
            ],
        },
        {
            "id": "outcomes",
            "title": "Outcomes",
            "fields": [
                {"id": "description", "type": "text", "required": False, "label": "Event Description"},
            ],
        },
    ],
    "validation_rules": [
        {"id": "r1", "rule": "date <= today", "severity": "error",
         "message": "Event date cannot be in the future"},
        {"id": "r2", "rule": "participant_count >= 0", "severity": "error",
         "message": "Participant count must be non-negative"},
        {"id": "r3", "rule": "photos.length >= 2", "severity": "error",
         "message": "At least 2 supporting photographs are required"},
    ],
}


def seed_naac_template():
    """Ensure the reference NAAC template + a local admin exist."""
    from app.models.models import Template, User, Organization
    from app.core.security import get_password_hash

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.name == "Demo Institution").first()
        if not org:
            org = Organization(name="Demo Institution")
            db.add(org)
            db.flush()

        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if not admin:
            admin = User(
                email="admin@example.com",
                name="Administrator",
                role="admin",
                org_id=org.id,
                password_hash=get_password_hash("admin12345"),
            )
            db.add(admin)
            db.flush()

        existing = db.query(Template).filter(
            Template.body == "NAAC",
            Template.name == "Criterion 3 - Extension Event Report",
            Template.version == "2025",
        ).first()

        if not existing:
            db.add(Template(
                body="NAAC",
                category="Criterion 3",
                name="Criterion 3 - Extension Event Report",
                version="2025",
                status="active",
                schema_json=NAAC_SCHEMA,
                last_verified=None,
                verified_by=admin.id,
                created_by=admin.id,
                source_url="https://naac.gov.in/",
            ))
            print("[seed] NAAC Criterion 3 template created (status=active)")
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[seed] skipped: {exc}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        print("[startup] database initialized")
    except Exception as exc:
        print(f"[startup] database unavailable: {exc}")
    try:
        seed_naac_template()
    except Exception as exc:
        print(f"[startup] seed failed: {exc}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Evidence-to-document compiler for accreditation submissions",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(projects.router)
app.include_router(files.router)
app.include_router(extractions.router)
app.include_router(validation.router)
app.include_router(documents.router)
app.include_router(audit.router)


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "scope": "evidence-to-document step only",
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}
