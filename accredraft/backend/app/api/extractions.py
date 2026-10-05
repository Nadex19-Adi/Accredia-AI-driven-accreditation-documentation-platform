"""Extraction review endpoints + pipeline triggers"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import (
    Project, Template, User, ExtractedField, FieldSource, EvidenceItem, File, AuditLog,
)
from app.schemas.schemas import (
    ExtractedFieldResponse, ExtractedFieldUpdate, BulkConfirmRequest, FieldSourceResponse,
)
from app.services import pipeline

router = APIRouter(prefix="/api", tags=["extraction"])


def _owned_project(db: Session, project_id: UUID, user: User) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role != "admin" and project.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this project")
    return project


# ── Pipeline triggers ─────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/process")
def trigger_process(
    project_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db, project_id, current_user)
    background.add_task(pipeline.process_files, str(project_id))
    return {"message": "Processing started", "stage": "ingestion"}


@router.post("/projects/{project_id}/extract")
def trigger_extract(
    project_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db, project_id, current_user)
    background.add_task(pipeline.run_extraction, str(project_id))
    return {"message": "Extraction started", "stage": "extraction"}


# ── Review ────────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/extractions", response_model=List[ExtractedFieldResponse])
def list_extractions(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _owned_project(db, project_id, current_user)
    template = db.query(Template).filter(Template.id == project.template_id).first()

    labels = {}
    types = {}
    for section in (template.schema_json or {}).get("sections", []) if template else []:
        for field in section.get("fields", []):
            labels[(section["id"], field["id"])] = field.get("label", field["id"])
            types[(section["id"], field["id"])] = field.get("type", "string")

    fields = (
        db.query(ExtractedField)
        .filter(ExtractedField.project_id == project.id)
        .order_by(ExtractedField.section_id, ExtractedField.field_id)
        .all()
    )

    out = []
    for f in fields:
        sources = []
        for src in f.sources:
            item = src.evidence_item
            file_name = None
            page = None
            if item:
                page = item.page
                file_rec = db.query(File).filter(File.id == item.file_id).first()
                file_name = file_rec.filename if file_rec else None
            sources.append(FieldSourceResponse(
                id=src.id,
                evidence_item_id=src.evidence_item_id,
                snippet=src.snippet,
                file_name=file_name,
                page=page,
            ))

        out.append(ExtractedFieldResponse(
            id=f.id,
            project_id=f.project_id,
            section_id=f.section_id,
            field_id=f.field_id,
            value_json=f.value_json,
            confidence=f.confidence,
            status=f.status,
            edited_by=f.edited_by,
            edited_at=f.edited_at,
            created_at=f.created_at,
            sources=sources,
            label=labels.get((f.section_id, f.field_id), f.field_id),
        ))
    return out


@router.put("/projects/{project_id}/extractions/{field_id}", response_model=ExtractedFieldResponse)
def update_extraction(
    project_id: UUID,
    field_id: UUID,
    data: ExtractedFieldUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _owned_project(db, project_id, current_user)
    record = db.query(ExtractedField).filter(
        ExtractedField.id == field_id,
        ExtractedField.project_id == project.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Extracted field not found")

    before = {"value": record.value_json, "status": record.status}

    if data.value is not None:
        record.value_json = data.value
        record.status = data.status or "edited"
    if data.status is not None:
        record.status = data.status
        if data.status == "missing":
            record.value_json = None

    record.edited_by = current_user.id
    record.edited_at = __import__("datetime").datetime.utcnow()

    db.add(AuditLog(
        user_id=current_user.id,
        project_id=project.id,
        action="field.update",
        before=before,
        after={"value": record.value_json, "status": record.status},
    ))
    db.commit()
    db.refresh(record)

    return ExtractedFieldResponse(
        id=record.id,
        project_id=record.project_id,
        section_id=record.section_id,
        field_id=record.field_id,
        value_json=record.value_json,
        confidence=record.confidence,
        status=record.status,
        edited_by=record.edited_by,
        edited_at=record.edited_at,
        created_at=record.created_at,
        sources=[],
    )


@router.post("/projects/{project_id}/extractions/bulk")
def bulk_confirm(
    project_id: UUID,
    data: BulkConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _owned_project(db, project_id, current_user)
    updated = 0
    for fid in data.field_ids:
        record = db.query(ExtractedField).filter(
            ExtractedField.id == fid,
            ExtractedField.project_id == project.id,
        ).first()
        if record:
            record.status = data.status
            record.edited_by = current_user.id
            updated += 1

    db.add(AuditLog(
        user_id=current_user.id,
        project_id=project.id,
        action="fields.bulk_status",
        after={"status": data.status, "count": updated},
    ))
    db.commit()
    return {"message": f"Updated {updated} fields", "count": updated}
