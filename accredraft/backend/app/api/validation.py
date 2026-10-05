"""Validation endpoints"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, User, ValidationRun
from app.schemas.schemas import ValidationRunResponse, ValidationResultResponse
from app.services import pipeline

router = APIRouter(prefix="/api", tags=["validation"])


def _owned_project(db: Session, project_id: UUID, user: User) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role != "admin" and project.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this project")
    return project


@router.post("/projects/{project_id}/validate")
def trigger_validation(
    project_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db, project_id, current_user)
    background.add_task(pipeline.run_validation, str(project_id))
    return {"message": "Validation started", "stage": "validation"}


@router.post("/projects/{project_id}/validate/sync")
def run_validation_sync(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run validation synchronously and return results (handy for the UI)."""
    _owned_project(db, project_id, current_user)
    result = pipeline.run_validation(str(project_id))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/projects/{project_id}/validation", response_model=ValidationRunResponse)
def get_latest_validation(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_project(db, project_id, current_user)

    run = (
        db.query(ValidationRun)
        .filter(ValidationRun.project_id == project_id)
        .order_by(ValidationRun.run_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="No validation run yet")

    results = [
        ValidationResultResponse(
            id=r.id, rule_id=r.rule_id, field_id=r.field_id,
            status=r.status, message=r.message, details=r.details,
        )
        for r in sorted(
            run.results,
            key=lambda x: {"error": 0, "warning": 1, "ok": 2}.get(x.status, 3),
        )
    ]

    return ValidationRunResponse(
        id=run.id, project_id=run.project_id,
        template_version=run.template_version, run_at=run.run_at,
        results=results,
    )
