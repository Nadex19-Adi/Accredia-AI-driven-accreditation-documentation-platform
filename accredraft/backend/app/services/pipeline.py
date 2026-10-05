"""
Background processing pipeline.

Each function is written to be callable both synchronously (FastAPI
BackgroundTasks / inline) and from an RQ worker. All DB access opens its own
session so it is safe to run outside the request lifecycle.
"""
import io
import json
import traceback
from datetime import datetime
from uuid import UUID

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import (
    Project, File, EvidenceItem, ExtractedField, FieldSource,
    Template, ValidationRun, ValidationResult, Document, GeneratedOutput,
)
from app.services.storage import get_storage
from app.services.file_parser import parse_file
from app.services.extractor import extract_fields
from app.services.validator import validate_fields
from app.services.renderer import get_renderer, convert_docx_to_pdf, MISSING_PLACEHOLDER


def _set_status(db, project: Project, status: str):
    project.status = status
    db.commit()


# ── Stage 1: ingestion ────────────────────────────────────────────────────────
def process_files(project_id: str) -> dict:
    """Parse every uploaded file into evidence_items."""
    db = SessionLocal()
    storage = get_storage()
    parsed = 0
    errors = []
    try:
        project = db.query(Project).filter(Project.id == UUID(project_id)).first()
        if not project:
            return {"error": "project not found"}

        _set_status(db, project, "processing")

        files = db.query(File).filter(File.project_id == project.id).all()
        for record in files:
            # Clear previous parse of this file (idempotent re-run)
            db.query(EvidenceItem).filter(EvidenceItem.file_id == record.id).delete()

            try:
                content = storage.download_file(record.storage_key)
            except Exception as exc:
                errors.append(f"{record.filename}: download failed ({exc})")
                continue

            try:
                items, page_count = parse_file(content, record.filename, record.mime)
            except Exception as exc:
                errors.append(f"{record.filename}: parse failed ({exc})")
                continue

            if page_count:
                record.page_count = page_count

            for item in items:
                db.add(EvidenceItem(
                    file_id=record.id,
                    page=item.page,
                    bbox=item.bbox,
                    item_type=item.item_type,
                    raw_text=item.raw_text,
                    ocr_confidence=item.ocr_confidence,
                    image_caption=item.image_caption,
                    classification=item.classification,
                ))
            parsed += 1

        db.commit()
        _set_status(db, project, "review")
        return {"parsed_files": parsed, "errors": errors}
    except Exception as exc:
        db.rollback()
        traceback.print_exc()
        return {"error": str(exc)}
    finally:
        db.close()


# ── Stage 2: extraction ───────────────────────────────────────────────────────
def run_extraction(project_id: str) -> dict:
    """LLM extraction of template fields from evidence, with provenance."""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == UUID(project_id)).first()
        if not project:
            return {"error": "project not found"}

        template = db.query(Template).filter(Template.id == project.template_id).first()
        if not template:
            return {"error": "template not found"}

        evidence = (
            db.query(EvidenceItem)
            .join(File, EvidenceItem.file_id == File.id)
            .filter(File.project_id == project.id)
            .all()
        )
        evidence_payload = [
            {
                "id": str(e.id),
                "page": e.page,
                "item_type": e.item_type,
                "raw_text": e.raw_text,
                "image_caption": e.image_caption,
                "classification": e.classification,
            }
            for e in evidence
        ]

        schema = template.schema_json or {}
        results = extract_fields(schema, evidence_payload)

        # Preserve human decisions: never clobber confirmed/edited/na fields.
        protected = {}
        for existing in db.query(ExtractedField).filter(ExtractedField.project_id == project.id).all():
            if existing.status in ("confirmed", "edited", "na"):
                protected[(existing.section_id, existing.field_id)] = existing

        # Remove stale auto fields that are no longer produced
        produced = set()
        field_section = {}
        for section in schema.get("sections", []):
            for field in section.get("fields", []):
                field_section[field["id"]] = section["id"]

        for result in results:
            section_id = field_section.get(result.field_id, "general")
            produced.add((section_id, result.field_id))

            if (section_id, result.field_id) in protected:
                continue

            db.query(ExtractedField).filter(
                ExtractedField.project_id == project.id,
                ExtractedField.section_id == section_id,
                ExtractedField.field_id == result.field_id,
            ).delete()

            extracted = ExtractedField(
                project_id=project.id,
                section_id=section_id,
                field_id=result.field_id,
                value_json=result.value,
                confidence=result.confidence,
                status="auto" if result.value is not None else "missing",
            )
            db.add(extracted)
            db.flush()

            for src in result.sources:
                evidence_id = src.get("evidence_id")
                try:
                    UUID(str(evidence_id))
                except (ValueError, TypeError):
                    evidence_id = None  # LLM may echo a non-UUID reference
                if evidence_id:
                    db.add(FieldSource(
                        extracted_field_id=extracted.id,
                        evidence_item_id=evidence_id,
                        snippet=(src.get("snippet") or "")[:2000],
                    ))

        # Seed any schema field the LLM did not mention as explicit 'missing'
        for section in schema.get("sections", []):
            for field in section.get("fields", []):
                key = (section["id"], field["id"])
                if key in produced:
                    continue
                exists = db.query(ExtractedField).filter(
                    ExtractedField.project_id == project.id,
                    ExtractedField.section_id == section["id"],
                    ExtractedField.field_id == field["id"],
                ).first()
                if not exists:
                    db.add(ExtractedField(
                        project_id=project.id,
                        section_id=section["id"],
                        field_id=field["id"],
                        value_json=None,
                        confidence=0.0,
                        status="missing",
                    ))

        db.commit()
        _set_status(db, project, "review")
        return {"extracted": len(results)}
    except Exception as exc:
        db.rollback()
        traceback.print_exc()
        return {"error": str(exc)}
    finally:
        db.close()


# ── Stage 3: validation ───────────────────────────────────────────────────────
def run_validation(project_id: str) -> dict:
    """Run template rules in code against current field values."""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == UUID(project_id)).first()
        if not project:
            return {"error": "project not found"}

        template = db.query(Template).filter(Template.id == project.template_id).first()
        if not template:
            return {"error": "template not found"}

        fields = db.query(ExtractedField).filter(ExtractedField.project_id == project.id).all()

        extracted_fields = {}
        for f in fields:
            extracted_fields.setdefault(f.section_id, {})[f.field_id] = {
                "value": f.value_json,
                "status": f.status,
            }

        checks = validate_fields(template.schema_json or {}, extracted_fields)

        run = ValidationRun(
            project_id=project.id,
            template_version=project.template_version,
        )
        db.add(run)
        db.flush()

        errors = warnings = oks = 0
        for check in checks:
            db.add(ValidationResult(
                run_id=run.id,
                rule_id=check.rule_id,
                field_id=check.field_id,
                status=check.status,
                message=check.message,
                details=check.details,
            ))
            if check.status == "error":
                errors += 1
            elif check.status == "warning":
                warnings += 1
            elif check.status == "ok":
                oks += 1

        db.commit()
        if errors == 0:
            _set_status(db, project, "validated")
        return {
            "run_id": str(run.id),
            "ok": oks,
            "errors": errors,
            "warnings": warnings,
        }
    except Exception as exc:
        db.rollback()
        traceback.print_exc()
        return {"error": str(exc)}
    finally:
        db.close()


# ── Stage 4: render ───────────────────────────────────────────────────────────
def _build_document_model(db, project: Project, template: Template) -> dict:
    fields = db.query(ExtractedField).filter(ExtractedField.project_id == project.id).all()
    by_section = {}
    for f in fields:
        by_section.setdefault(f.section_id, {})[f.field_id] = f

    sections = []
    for section in (template.schema_json or {}).get("sections", []):
        out_fields = {}
        for field in section.get("fields", []):
            record = by_section.get(section["id"], {}).get(field["id"])
            if record is None:
                out_fields[field["id"]] = {
                    "value": None, "status": "missing",
                    "label": field.get("label", field["id"]),
                }
                continue
            out_fields[field["id"]] = {
                "value": record.value_json,
                "status": record.status,
                "confidence": record.confidence,
                "label": field.get("label", field["id"]),
            }
        sections.append({"id": section["id"], "title": section.get("title", section["id"]), "fields": out_fields})

    return {
        "template_id": (template.schema_json or {}).get("template_id", str(template.id)),
        "template_version": project.template_version,
        "generated_at": datetime.utcnow().isoformat(),
        "sections": sections,
    }


def generate_document(project_id: str, user_id: str | None = None) -> dict:
    """Render the confirmed document model to DOCX (and PDF if available)."""
    db = SessionLocal()
    storage = get_storage()
    try:
        project = db.query(Project).filter(Project.id == UUID(project_id)).first()
        if not project:
            return {"error": "project not found"}

        template = db.query(Template).filter(Template.id == project.template_id).first()
        if not template:
            return {"error": "template not found"}

        doc_model = _build_document_model(db, project, template)

        doc_record = Document(
            project_id=project.id,
            doc_model_json=doc_model,
            version=(db.query(Document).filter(Document.project_id == project.id).count() + 1),
        )
        db.add(doc_record)
        db.flush()

        renderer = get_renderer()
        docx_bytes = renderer.render(doc_model, template.layout_template_path)
        docx_bytes = renderer.add_page_numbers(docx_bytes)

        docx_key = storage.upload_generated_document(
            docx_bytes, project.id, "docx", project.template_version
        )
        db.add(GeneratedOutput(
            document_id=doc_record.id,
            format="docx",
            storage_key=docx_key,
            template_version=project.template_version,
            created_by=UUID(user_id) if user_id else None,
        ))

        pdf_key = None
        pdf_bytes = convert_docx_to_pdf(docx_bytes)
        if pdf_bytes:
            pdf_key = storage.upload_generated_document(
                pdf_bytes, project.id, "pdf", project.template_version
            )
            db.add(GeneratedOutput(
                document_id=doc_record.id,
                format="pdf",
                storage_key=pdf_key,
                template_version=project.template_version,
                created_by=UUID(user_id) if user_id else None,
            ))

        db.commit()
        _set_status(db, project, "generated")

        return {
            "document_id": str(doc_record.id),
            "docx_key": docx_key,
            "pdf_key": pdf_key,
            "pdf_available": pdf_bytes is not None,
        }
    except Exception as exc:
        db.rollback()
        traceback.print_exc()
        return {"error": str(exc)}
    finally:
        db.close()
