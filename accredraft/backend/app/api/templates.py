"""Template management endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.models import Template, User
from app.schemas.schemas import TemplateCreate, TemplateUpdate, TemplateResponse
import os
import shutil
from app.core.config import settings

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=List[TemplateResponse])
def list_templates(
    body: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Template)
    
    if body:
        query = query.filter(Template.body == body)
    if status:
        query = query.filter(Template.status == status)
    
    # Non-admins only see active/verified templates
    if current_user.role != "admin":
        query = query.filter(Template.status.in_(["active", "verified"]))
    
    return query.order_by(Template.body, Template.name, Template.version.desc()).all()


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("", response_model=TemplateResponse)
def create_template(
    data: TemplateCreate,
    layout_file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Check for duplicate
    existing = db.query(Template).filter(
        Template.body == data.body,
        Template.name == data.name,
        Template.version == data.version,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Template version already exists")
    
    # Handle layout template upload
    layout_path = None
    if layout_file:
        os.makedirs(settings.LAYOUT_TEMPLATES_DIR, exist_ok=True)
        layout_path = os.path.join(
            settings.LAYOUT_TEMPLATES_DIR,
            f"{data.body}_{data.name}_{data.version}.docx"
        )
        with open(layout_path, "wb") as f:
            shutil.copyfileobj(layout_file.file, f)
    
    template = Template(
        body=data.body,
        category=data.category,
        name=data.name,
        version=data.version,
        schema_json=data.schema_json,
        source_url=data.source_url,
        date_retrieved=data.date_retrieved,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
        layout_template_path=layout_path,
        status="draft",
        created_by=current_user.id,
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: UUID,
    data: TemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    
    db.commit()
    db.refresh(template)
    return template


@router.get("/{template_id}/layout")
def download_layout(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi.responses import FileResponse
    
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template or not template.layout_template_path:
        raise HTTPException(status_code=404, detail="Layout template not found")
    
    if not os.path.exists(template.layout_template_path):
        raise HTTPException(status_code=404, detail="Layout template file not found")
    
    return FileResponse(
        template.layout_template_path,
        filename=f"{template.name}_{template.version}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/{template_id}/publish", response_model=TemplateResponse)
def publish_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Publish a template (mark as active)"""
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    if template.status not in ["draft", "verified"]:
        raise HTTPException(status_code=400, detail="Can only publish draft or verified templates")
    
    # Mark previous active templates as superseded
    db.query(Template).filter(
        Template.body == template.body,
        Template.name == template.name,
        Template.status == "active",
    ).update({"status": "superseded"})
    
    template.status = "active"
    template.last_verified = func.now()  # type: ignore
    template.verified_by = current_user.id
    
    db.commit()
    db.refresh(template)
    return template


from sqlalchemy import func