"""File upload and evidence endpoints"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as UploadFileParam
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import io
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.models import File, Project, User, EvidenceItem, AuditLog
from app.schemas.schemas import FileResponse, EvidenceItemResponse
from app.services.storage import get_storage
from app.services.file_parser import get_file_kind

router = APIRouter(prefix="/api", tags=["files"])


def _get_owned_project(db: Session, project_id: UUID, user: User) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role != "admin" and project.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this project")
    return project


@router.post("/projects/{project_id}/files", response_model=List[FileResponse])
async def upload_files(
    project_id: UUID,
    files: List[UploadFile] = UploadFileParam(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_owned_project(db, project_id, current_user)
    storage = get_storage()
    created = []

    for upload in files:
        if upload.filename is None:
            continue

        ext = "." + upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type not allowed: {upload.filename}")

        content = await upload.read()
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File too large: {upload.filename}")

        # Re-wrap so storage can re-read
        await upload.seek(0)
        storage_key, sha256 = await storage.upload_file(upload, project.id)

        record = File(
            project_id=project.id,
            storage_key=storage_key,
            filename=upload.filename,
            mime=upload.content_type or "application/octet-stream",
            sha256=sha256,
            file_kind=get_file_kind(upload.content_type or "", upload.filename),
        )
        db.add(record)
        db.flush()
        created.append(record)

    db.add(AuditLog(
        user_id=current_user.id,
        project_id=project.id,
        action="files.upload",
        after={"count": len(created), "filenames": [f.filename for f in created]},
    ))
    db.commit()
    for rec in created:
        db.refresh(rec)
    return created


@router.get("/projects/{project_id}/files", response_model=List[FileResponse])
def list_files(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)
    return db.query(File).filter(File.project_id == project_id).order_by(File.created_at).all()


@router.delete("/files/{file_id}")
def delete_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.query(File).filter(File.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    _get_owned_project(db, record.project_id, current_user)

    try:
        get_storage().delete_file(record.storage_key)
    except Exception:
        pass

    db.delete(record)
    db.commit()
    return {"message": "File deleted"}


@router.get("/files/{file_id}/evidence", response_model=List[EvidenceItemResponse])
def get_evidence(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.query(File).filter(File.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    _get_owned_project(db, record.project_id, current_user)

    items = db.query(EvidenceItem).filter(EvidenceItem.file_id == file_id).order_by(EvidenceItem.page).all()
    out = []
    for item in items:
        data = EvidenceItemResponse.model_validate(item)
        data.filename = record.filename
        out.append(data)
    return out


@router.get("/files/{file_id}/download")
def download_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.query(File).filter(File.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    _get_owned_project(db, record.project_id, current_user)

    try:
        content = get_storage().download_file(record.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File unavailable: {exc}")

    return StreamingResponse(
        io.BytesIO(content),
        media_type=record.mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )
