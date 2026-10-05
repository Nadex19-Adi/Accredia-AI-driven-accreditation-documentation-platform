"""Project management endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Template, User, AuditLog
from app.schemas.schemas import ProjectCreate, ProjectUpdate, ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    status: Optional[str] = None,
    template_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Project)
    
    if current_user.role != "admin":
        query = query.filter(Project.created_by == current_user.id)
    
    if status:
        query = query.filter(Project.status == status)
    if template_id:
        query = query.filter(Project.template_id == template_id)
    
    return query.order_by(Project.updated_at.desc()).all()


@router.post("", response_model=ProjectResponse)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify template exists
    template = db.query(Template).filter(Template.id == data.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check for active/verified template
    if template.status not in ["active", "verified"]:
        raise HTTPException(
            status_code=400,
            detail=f"Template status is '{template.status}'. Only active or verified templates can be used."
        )
    
    project = Project(
        template_id=data.template_id,
        template_version=template.version,  # Pin version at creation
        name=data.name,
        description=data.description,
        org_id=current_user.org_id,
        created_by=current_user.id,
    )
    db.add(project)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="project.create",
        after={"project_id": str(project.id), "name": data.name, "template_version": template.version},
    )
    db.add(audit)
    
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    before = {"status": project.status, "name": project.name}
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    
    audit = AuditLog(
        user_id=current_user.id,
        project_id=project_id,
        action="project.update",
        before=before,
        after=data.model_dump(exclude_unset=True),
    )
    db.add(audit)
    
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    audit = AuditLog(
        user_id=current_user.id,
        project_id=project_id,
        action="project.delete",
        before={"name": project.name},
    )
    db.add(audit)
    
    db.delete(project)
    db.commit()
    return {"message": "Project deleted"}


@router.post("/{project_id}/migrate")
def migrate_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Migrate project to a newer template version"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Find next version of template
    template = db.query(Template).filter(
        Template.id == project.template_id,
        Template.version > project.template_version,
        Template.status.in_(["active", "verified"]),
    ).order_by(Template.version).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="No newer template version found")
    
    audit = AuditLog(
        user_id=current_user.id,
        project_id=project_id,
        action="project.migrate",
        before={"template_version": project.template_version},
        after={"template_version": template.version},
    )
    db.add(audit)
    
    project.template_version = template.version
    project.status = "draft"  # Reset status after migration
    
    db.commit()
    db.refresh(project)
    
    return {
        "message": f"Project migrated to version {template.version}",
        "old_version": project.template_version,
        "new_version": template.version,
    }
