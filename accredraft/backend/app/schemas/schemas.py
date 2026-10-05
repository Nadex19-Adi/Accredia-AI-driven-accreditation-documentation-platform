from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any, Dict
from datetime import datetime, date
from uuid import UUID
import warnings

# `schema_json` intentionally mirrors the DB column name. Pydantic v2 warns that
# it shadows the deprecated BaseModel.schema_json(); the shadowing is harmless
# here because these models only ever read the attribute from the ORM object.
warnings.filterwarnings(
    "ignore",
    message=r'Field name "schema_json".*shadows an attribute',
    category=UserWarning,
)


# ── Auth ──────────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    org_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: Optional[str]
    role: str
    org_id: Optional[UUID]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ── Organization ───────────────────────────────────────────────────────────────
class OrgCreate(BaseModel):
    name: str


class OrgResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# ── Template ───────────────────────────────────────────────────────────────────
class TemplateFieldSchema(BaseModel):
    id: str
    type: str  # string, date, integer, text, text[], image[], file
    required: bool = False
    label: Optional[str] = None
    min_items: Optional[int] = None
    min: Optional[int] = None
    caption_required: bool = False


class TemplateSectionSchema(BaseModel):
    id: str
    title: str
    fields: List[TemplateFieldSchema]


class ValidationRuleSchema(BaseModel):
    id: str
    rule: str
    severity: str  # error, warning
    message: str


class TemplateSchema(BaseModel):
    template_id: str
    body: str
    version: str
    sections: List[TemplateSectionSchema]
    validation_rules: List[ValidationRuleSchema]


class TemplateCreate(BaseModel):
    body: str
    category: str
    name: str
    version: str
    schema_json: Dict[str, Any]
    source_url: Optional[str] = None
    date_retrieved: Optional[date] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    layout_template_path: Optional[str] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    last_verified: Optional[date] = None
    verified_by: Optional[UUID] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    schema_json: Optional[Dict[str, Any]] = None
    layout_template_path: Optional[str] = None


class TemplateResponse(BaseModel):
    id: UUID
    body: str
    category: str
    name: str
    version: str
    status: str
    source_url: Optional[str]
    date_retrieved: Optional[date]
    last_verified: Optional[date]
    verified_by: Optional[UUID]
    valid_from: Optional[date]
    valid_to: Optional[date]
    schema_json: Dict[str, Any]
    layout_template_path: Optional[str]
    doc_hash: Optional[str]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ── Project ────────────────────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    template_id: UUID
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    id: UUID
    org_id: Optional[UUID]
    template_id: UUID
    template_version: str
    name: str
    description: Optional[str]
    status: str
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ── File ──────────────────────────────────────────────────────────────────────
class FileResponse(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    mime: str
    sha256: Optional[str]
    page_count: Optional[int]
    file_kind: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ── Evidence Item ─────────────────────────────────────────────────────────────
class EvidenceItemResponse(BaseModel):
    id: UUID
    file_id: UUID
    filename: Optional[str] = None
    page: Optional[int]
    bbox: Optional[Dict[str, Any]]
    item_type: str
    raw_text: Optional[str]
    ocr_confidence: Optional[float]
    image_caption: Optional[str]
    classification: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ── Extracted Field ───────────────────────────────────────────────────────────
class FieldSourceResponse(BaseModel):
    id: UUID
    evidence_item_id: UUID
    snippet: Optional[str]
    file_name: Optional[str] = None
    page: Optional[int] = None
    
    class Config:
        from_attributes = True


class ExtractedFieldValue(BaseModel):
    """Wrapper for extracted field value with status"""
    value: Any
    status: str  # auto, confirmed, edited, missing, na
    sources: List[UUID] = []
    edited_value: Optional[Any] = None


class ExtractedFieldUpdate(BaseModel):
    status: Optional[str] = None
    value: Optional[Any] = None


class ExtractedFieldResponse(BaseModel):
    id: UUID
    project_id: UUID
    section_id: str
    field_id: str
    value_json: Optional[Any]
    confidence: Optional[float]
    status: str
    edited_by: Optional[UUID]
    edited_at: Optional[datetime]
    created_at: datetime
    sources: List[FieldSourceResponse] = []
    label: Optional[str] = None
    
    class Config:
        from_attributes = True


class BulkConfirmRequest(BaseModel):
    field_ids: List[UUID]
    status: str = "confirmed"


# ── Validation ─────────────────────────────────────────────────────────────────
class ValidationResultResponse(BaseModel):
    id: UUID
    rule_id: str
    field_id: Optional[str]
    status: str  # ok, error, warning
    message: Optional[str]
    details: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True


class ValidationRunResponse(BaseModel):
    id: UUID
    project_id: UUID
    template_version: str
    run_at: datetime
    results: List[ValidationResultResponse] = []
    
    class Config:
        from_attributes = True


# ── Document ───────────────────────────────────────────────────────────────────
class DocumentModelSection(BaseModel):
    id: str
    title: str
    fields: Dict[str, Any]


class DocumentModel(BaseModel):
    template_id: str
    template_version: str
    generated_at: datetime
    sections: List[DocumentModelSection]


class DocumentResponse(BaseModel):
    id: UUID
    project_id: UUID
    doc_model_json: Dict[str, Any]
    version: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class GeneratedOutputResponse(BaseModel):
    id: UUID
    document_id: UUID
    format: str
    storage_key: str
    template_version: str
    created_by: Optional[UUID]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ── Audit Log ─────────────────────────────────────────────────────────────────
class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    project_id: Optional[UUID]
    action: str
    before: Optional[Dict[str, Any]]
    after: Optional[Dict[str, Any]]
    ts: datetime
    
    class Config:
        from_attributes = True


# ── API Responses ──────────────────────────────────────────────────────────────
class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int
