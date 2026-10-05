import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.types import GUID as UUID, JSONType as JSONB


class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    users = relationship("User", back_populates="organization")
    projects = relationship("Project", back_populates="organization")


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(), ForeignKey("organizations.id"))
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    role = Column(String(50), default="editor")  # admin, editor, viewer
    password_hash = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    organization = relationship("Organization", back_populates="users")
    projects = relationship("Project", back_populates="creator")
    audit_logs = relationship("AuditLog", back_populates="user")


class Template(Base):
    __tablename__ = "templates"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    body = Column(String(100), nullable=False, index=True)  # NAAC, NBA, NEC
    category = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    version = Column(String(20), nullable=False)
    status = Column(String(20), default="draft", index=True)  # draft, verified, active, superseded, deprecated
    source_url = Column(Text)
    date_retrieved = Column(Date)
    last_verified = Column(Date)
    verified_by = Column(UUID(), ForeignKey("users.id"))
    valid_from = Column(Date)
    valid_to = Column(Date)
    schema_json = Column(JSONB, nullable=False)
    layout_template_path = Column(String(500))  # path to layout .docx file
    doc_hash = Column(String(64))
    created_by = Column(UUID(), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    projects = relationship("Project", back_populates="template")
    
    # Composite unique: body + name + version
    __table_args__ = (
        # Unique constraint handled in code
    )


class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(), ForeignKey("organizations.id"))
    template_id = Column(UUID(), ForeignKey("templates.id"))
    template_version = Column(String(20), nullable=False)  # Pinned at creation
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="draft", index=True)  # draft, processing, review, validated, generated
    created_by = Column(UUID(), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    organization = relationship("Organization", back_populates="projects")
    template = relationship("Template", back_populates="projects")
    creator = relationship("User", back_populates="projects")
    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    extracted_fields = relationship("ExtractedField", back_populates="project", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    validation_runs = relationship("ValidationRun", back_populates="project", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="project")


class File(Base):
    __tablename__ = "files"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(), ForeignKey("projects.id"))
    storage_key = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    mime = Column(String(100), nullable=False)
    sha256 = Column(String(64))
    page_count = Column(Integer)
    file_kind = Column(String(50))  # pdf, docx, image, xlsx
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="files")
    evidence_items = relationship("EvidenceItem", back_populates="file", cascade="all, delete-orphan")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(), ForeignKey("files.id"))
    page = Column(Integer)
    bbox = Column(JSONB)  # {x, y, width, height}
    item_type = Column(String(50), nullable=False)  # text, table, image
    raw_text = Column(Text)
    ocr_confidence = Column(Float)  # 0-1
    image_caption = Column(Text)
    classification = Column(String(100))  # certificate, photo, poster, attendance_sheet
    created_at = Column(DateTime, default=datetime.utcnow)
    
    file = relationship("File", back_populates="evidence_items")
    field_sources = relationship("FieldSource", back_populates="evidence_item", cascade="all, delete-orphan")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(), ForeignKey("projects.id"))
    section_id = Column(String(100), nullable=False)
    field_id = Column(String(100), nullable=False)
    value_json = Column(JSONB)  # The extracted value
    confidence = Column(Float)
    status = Column(String(50), default="auto")  # auto, confirmed, edited, missing, na
    edited_by = Column(UUID(), ForeignKey("users.id"))
    edited_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="extracted_fields")
    sources = relationship("FieldSource", back_populates="extracted_field", cascade="all, delete-orphan")
    editor = relationship("User", foreign_keys=[edited_by])
    
    __table_args__ = (
        # Unique constraint on project_id + section_id + field_id
    )


class FieldSource(Base):
    __tablename__ = "field_sources"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    extracted_field_id = Column(UUID(), ForeignKey("extracted_fields.id"))
    evidence_item_id = Column(UUID(), ForeignKey("evidence_items.id"))
    snippet = Column(Text)  # The quoted source text
    created_at = Column(DateTime, default=datetime.utcnow)
    
    extracted_field = relationship("ExtractedField", back_populates="sources")
    evidence_item = relationship("EvidenceItem", back_populates="field_sources")


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(), ForeignKey("projects.id"))
    template_version = Column(String(20), nullable=False)
    run_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="validation_runs")
    results = relationship("ValidationResult", back_populates="run", cascade="all, delete-orphan")


class ValidationResult(Base):
    __tablename__ = "validation_results"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(), ForeignKey("validation_runs.id"))
    rule_id = Column(String(100), nullable=False)
    field_id = Column(String(100))
    status = Column(String(20), nullable=False)  # ok, error, warning
    message = Column(Text)
    details = Column(JSONB)
    
    run = relationship("ValidationRun", back_populates="results")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(), ForeignKey("projects.id"))
    doc_model_json = Column(JSONB, nullable=False)  # Canonical document model
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="documents")
    outputs = relationship("GeneratedOutput", back_populates="document", cascade="all, delete-orphan")


class GeneratedOutput(Base):
    __tablename__ = "generated_outputs"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(), ForeignKey("documents.id"))
    format = Column(String(20), nullable=False)  # docx, pdf
    storage_key = Column(String(500), nullable=False)
    template_version = Column(String(20), nullable=False)
    created_by = Column(UUID(), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship("Document", back_populates="outputs")
    creator = relationship("User", foreign_keys=[created_by])


class AuditLog(Base):
    __tablename__ = "audit_log"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(), ForeignKey("users.id"))
    project_id = Column(UUID(), ForeignKey("projects.id"))
    action = Column(String(100), nullable=False)
    before = Column(JSONB)
    after = Column(JSONB)
    ts = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="audit_logs")
    project = relationship("Project", back_populates="audit_logs")
