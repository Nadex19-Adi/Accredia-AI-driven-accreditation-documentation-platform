"""Document generation and download endpoints"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import io
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, User, Document, GeneratedOutput, AuditLog
from app.schemas.schemas import DocumentResponse, GeneratedOutputResponse
from app.services import pipeline
from app.services.storage import get_storage

router = APIRouter(prefix="/api", tags=["documents"])


def _owned_project(db: Session, project_id: UUID, user: User) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role != "admin" and project.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this project")
    return project


@router.post("/projects/{project_id}/generate")
def trigger_generate(
    project_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db, project_id, current_user)
    background.add_task(pipeline.generate_document, str(project_id), str(current_user.id))
    return {"message": "Generation started", "stage": "render"}


@router.post("/projects/{project_id}/generate/sync")
def generate_sync(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate synchronously and return output keys."""
    _owned_project(db, project_id, current_user)
    result = pipeline.generate_document(str(project_id), str(current_user.id))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/projects/{project_id}/documents", response_model=List[DocumentResponse])
def list_documents(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db, project_id, current_user)
    docs = (
        db.query(Document)
        .filter(Document.project_id == project_id)
        .order_by(Document.version.desc())
        .all()
    )
    return docs


@router.get("/projects/{project_id}/outputs", response_model=List[GeneratedOutputResponse])
def list_outputs(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db, project_id, current_user)
    doc_ids = [d.id for d in db.query(Document).filter(Document.project_id == project_id).all()]
    if not doc_ids:
        return []
    return (
        db.query(GeneratedOutput)
        .filter(GeneratedOutput.document_id.in_(doc_ids))
        .order_by(GeneratedOutput.created_at.desc())
        .all()
    )


@router.get("/outputs/{output_id}/download")
def download_output(
    output_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    output = db.query(GeneratedOutput).filter(GeneratedOutput.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    document = db.query(Document).filter(Document.id == output.document_id).first()
    if document:
        _owned_project(db, document.project_id, current_user)

    storage = get_storage()
    try:
        content = storage.download_file(output.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File unavailable: {exc}")

    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if output.format == "docx" else "application/pdf"
    )
    filename = f"report_v{output.template_version}.{output.format}"

    db.add(AuditLog(
        user_id=current_user.id,
        project_id=document.project_id if document else None,
        action="output.download",
        after={"format": output.format, "key": output.storage_key},
    ))
    db.commit()

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
