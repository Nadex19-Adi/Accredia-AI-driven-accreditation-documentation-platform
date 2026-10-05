"""
File parsing service: extracts evidence items from uploaded files.
Supports: PDF, DOCX, Images (JPG/PNG), XLSX
"""
try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 module name
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz
import docx
import openpyxl
import pytesseract
from PIL import Image
from io import BytesIO
from typing import List, Dict, Any, Optional
import uuid


class EvidenceItem:
    def __init__(
        self,
        item_type: str,
        raw_text: str = None,
        page: int = None,
        bbox: dict = None,
        ocr_confidence: float = None,
        image_caption: str = None,
        classification: str = None,
    ):
        self.id = uuid.uuid4()
        self.item_type = item_type
        self.raw_text = raw_text
        self.page = page
        self.bbox = bbox
        self.ocr_confidence = ocr_confidence
        self.image_caption = image_caption
        self.classification = classification


def parse_pdf(content: bytes) -> List[EvidenceItem]:
    """Parse PDF text using PyMuPDF. Falls back to OCR if text layer is empty."""
    items = []
    doc = fitz.open(stream=content, filetype="pdf")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        
        if text:
            # Extract text blocks with positions
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") == 0:  # text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            bbox = {
                                "x": span["bbox"][0],
                                "y": span["bbox"][1],
                                "width": span["bbox"][2] - span["bbox"][0],
                                "height": span["bbox"][3] - span["bbox"][1],
                            }
                            items.append(EvidenceItem(
                                item_type="text",
                                raw_text=span["text"].strip(),
                                page=page_num + 1,
                                bbox=bbox,
                            ))
        else:
            # Scanned page - use OCR
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            img = Image.open(BytesIO(img_bytes))
            
            text = pytesseract.image_to_string(img)
            items.append(EvidenceItem(
                item_type="text",
                raw_text=text.strip(),
                page=page_num + 1,
                ocr_confidence=0.7,
            ))
    
    doc.close()
    return items


def parse_docx(content: bytes) -> List[EvidenceItem]:
    """Parse DOCX text and tables using python-docx."""
    items = []
    doc = docx.Document(BytesIO(content))
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            items.append(EvidenceItem(
                item_type="text",
                raw_text=text,
            ))
    
    for table in doc.tables:
        table_text = []
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells)
            if row_text:
                table_text.append(row_text)
        
        if table_text:
            items.append(EvidenceItem(
                item_type="table",
                raw_text="\n".join(table_text),
            ))
    
    return items


def parse_image(content: bytes, filename: str = "") -> List[EvidenceItem]:
    """Parse image using OCR and classify content."""
    img = Image.open(BytesIO(content))
    
    # OCR
    text = pytesseract.image_to_string(img)
    
    # Classify image type based on common keywords
    text_lower = text.lower()
    classification = "photo"
    
    if any(kw in text_lower for kw in ["certificate", "certified", "award", "certificate of"]):
        classification = "certificate"
    elif any(kw in text_lower for kw in ["attendance", "present", "signature", "roll call"]):
        classification = "attendance_sheet"
    elif any(kw in text_lower for kw in ["poster", "banner", "flyer", "notice"]):
        classification = "poster"
    elif any(kw in text_lower for kw in ["agenda", "schedule", "program", "itinerary"]):
        classification = "agenda"
    
    # Try to get caption from nearby text or use filename
    caption = None
    if filename:
        # Extract potential caption from filename
        import re
        # Remove extension and clean up
        caption = re.sub(r'[_-]+', ' ', filename.rsplit('.', 1)[0]).strip()
    
    return [
        EvidenceItem(
            item_type="image",
            raw_text=text.strip() if text.strip() else None,
            ocr_confidence=0.8,
            image_caption=caption,
            classification=classification,
        )
    ]


def parse_xlsx(content: bytes) -> List[EvidenceItem]:
    """Parse XLSX attendance sheets."""
    items = []
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        rows_text = []
        
        for row in sheet.iter_rows(values_only=True):
            row_text = " | ".join(
                str(cell) if cell is not None else ""
                for cell in row
            ).strip()
            if row_text and row_text != " | ":
                rows_text.append(row_text)
        
        if rows_text:
            # Try to detect participant count
            participant_count = None
            for row_text in rows_text:
                if "total" in row_text.lower() or "count" in row_text.lower():
                    import re
                    nums = re.findall(r'\d+', row_text)
                    if nums:
                        participant_count = int(nums[-1])
                        break
            
            items.append(EvidenceItem(
                item_type="table",
                raw_text="\n".join(rows_text),
            ))
    
    return items


def parse_file(content: bytes, filename: str, mime: str, page_count: int = None) -> tuple[List[EvidenceItem], Optional[int]]:
    """
    Parse uploaded file and return evidence items.
    Returns (items, detected_page_count)
    """
    mime = mime.lower()
    
    if mime == "application/pdf" or filename.lower().endswith(".pdf"):
        items = parse_pdf(content)
        doc = fitz.open(stream=content, filetype="pdf")
        page_count = len(doc)
        doc.close()
        return items, page_count
    
    elif mime in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword") or \
         filename.lower().endswith((".docx", ".doc")):
        return parse_docx(content), 1
    
    elif mime.startswith("image/"):
        return parse_image(content, filename), 1
    
    elif mime in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel") or \
         filename.lower().endswith((".xlsx", ".xls")):
        return parse_xlsx(content), 1
    
    else:
        # Try to detect from content
        return [], None


def get_file_kind(mime: str, filename: str) -> str:
    """Determine file kind from mime and filename."""
    mime = mime.lower()
    
    if mime == "application/pdf" or filename.lower().endswith(".pdf"):
        return "pdf"
    elif "wordprocessingml" in mime or filename.lower().endswith((".docx", ".doc")):
        return "docx"
    elif mime.startswith("image/"):
        return "image"
    elif "spreadsheet" in mime or filename.lower().endswith((".xlsx", ".xls")):
        return "xlsx"
    else:
        return "unknown"
