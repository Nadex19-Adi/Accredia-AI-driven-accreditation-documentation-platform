"""Audit log endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import AuditLog, Project, User
from app.schemas.schemas import AuditLogResponse

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/projects/{project_id}/audit", response_model=List[AuditLogResponse])
def project_audit(
    project_id: UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role != "admin" and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this project")

    return (
        db.query(AuditLog)
        .filter(AuditLog.project_id == project_id)
        .order_by(AuditLog.ts.desc())
        .limit(limit)
        .all()
    )


@router.get("/audit", response_model=List[AuditLogResponse])
def global_audit(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).all()
