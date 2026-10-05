"""
LLM-based field extraction service.
Extracts structured fields from evidence items using a field schema.
"""
import json
from typing import Any, Dict, List, Optional
from openai import OpenAI
from app.core.config import settings


class ExtractionResult:
    def __init__(
        self,
        field_id: str,
        value: Any,
        confidence: float,
        sources: List[Dict[str, Any]],  # [{evidence_item_id, snippet}]
    ):
        self.field_id = field_id
        self.value = value
        self.confidence = confidence
        self.sources = sources


def build_extraction_prompt(schema: Dict[str, Any], evidence_context: str) -> str:
    """Build the prompt for LLM extraction."""
    
    field_descriptions = []
    for section in schema.get("sections", []):
        for field in section.get("fields", []):
            field_type = field.get("type", "string")
            required = field.get("required", False)
            label = field.get("label", field["id"])
            
            desc = f'- {field["id"]}: {field_type}'
            if field.get("min_items"):
                desc += f' (min {field["min_items"]} items)'
            if required:
                desc += ' [REQUIRED]'
            desc += f'\n    Label: {label}'
            field_descriptions.append(desc)
    
    field_descriptions_str = "\n".join(field_descriptions)
    
    prompt = f"""You are an evidence extraction system for institutional accreditation reports.

Your task is to extract structured field values from the provided evidence text.
IMPORTANT RULES:
- ONLY extract values that you can find in the evidence text
- If a value is NOT found, return null for that field
- NEVER invent or hallucinate values
- Be conservative and precise
- Dates should be in YYYY-MM-DD format
- Numbers should be actual numbers, not strings
- For text fields, return the actual extracted text
- For text[] fields, return an array of strings
- For image[] fields, return an array with image descriptions
- Confidence scores should reflect how certain you are (0.0-1.0)

Available fields to extract:
{field_descriptions_str}

Evidence text (from uploaded files):
---
{evidence_context[:15000]}  # Truncate to avoid token limits
---

Output format (JSON only, no other text):
{{
  "extractions": [
    {{
      "field_id": "field_id_here",
      "value": <extracted_value_or_null>,
      "confidence": 0.85,
      "sources": [
        {{"evidence_id": "ref1", "snippet": "the actual text found"}}
      ]
    }}
  ]
}}

Return ONLY valid JSON. No markdown, no explanation."""
    
    return prompt


def extract_fields(schema: Dict[str, Any], evidence_items: List[Dict[str, Any]]) -> List[ExtractionResult]:
    """Extract structured fields from evidence using LLM."""
    
    # Build evidence context
    evidence_context_lines = []
    for item in evidence_items:
        if item.get("raw_text"):
            page_info = f"[Page {item['page']}] " if item.get("page") else ""
            evidence_context_lines.append(f"{page_info}[{item['item_type']}] {item['raw_text'][:2000]}")
    
    evidence_context = "\n\n---\n\n".join(evidence_context_lines)
    
    if not evidence_context.strip():
        return []
    
    # Check if API key is set
    if not settings.OPENAI_API_KEY:
        return _extract_fallback(evidence_items, schema)
    
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        prompt = build_extraction_prompt(schema, evidence_context)
        
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise evidence extraction system. Always output valid JSON. Never hallucinate."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for extraction
            response_format={"type": "json_object"},
            max_tokens=4000,
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        
        results = []
        for extraction in data.get("extractions", []):
            results.append(ExtractionResult(
                field_id=extraction["field_id"],
                value=extraction.get("value"),
                confidence=extraction.get("confidence", 0.5),
                sources=extraction.get("sources", []),
            ))
        
        return results
    
    except Exception as e:
        print(f"LLM extraction failed: {e}")
        # Fallback: simple keyword extraction
        return _extract_fallback(evidence_items, schema)


def _extract_fallback(evidence_items: List[Dict[str, Any]], schema: Dict[str, Any]) -> List[ExtractionResult]:
    """
    Fallback extraction using simple keyword matching.
    Used when LLM is unavailable or fails.
    """
    results = []
    # Join with newlines so line-anchored patterns ([^\n]) stay within a line.
    # Keep original casing: all patterns below are case-insensitive.
    all_text = "\n".join(
        item.get("raw_text", "") or ""
        for item in evidence_items
    )
    
    for section in schema.get("sections", []):
        for field in section.get("fields", []):
            field_id = field["id"]
            field_type = field.get("type", "string")
            
            value = None
            confidence = 0.0
            
            # Simple keyword extraction
            if field_id == "title":
                import re
                # Look for "Title:" or "Event Name:" patterns
                match = re.search(r'(?:title|event name|report name)[:\s]+([^\n]{5,100})', all_text, re.I)
                if match:
                    value = match.group(1).strip()
                    confidence = 0.6
            
            elif field_id == "date":
                import re
                from datetime import datetime
                # Try various date formats
                patterns = [
                    r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',
                    r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',
                    r'[A-Za-z]+ \d{1,2},? \d{4}',
                    r'\d{1,2} [A-Za-z]+ \d{4}',
                ]
                for pattern in patterns:
                    match = re.search(pattern, all_text)
                    if match:
                        try:
                            # Try to parse
                            date_str = match.group()
                            for fmt in ['%d-%m-%Y', '%m-%d-%Y', '%Y-%m-%d', '%B %d, %Y', '%d %B %Y']:
                                try:
                                    dt = datetime.strptime(date_str, fmt)
                                    value = dt.strftime('%Y-%m-%d')
                                    confidence = 0.5
                                    break
                                except ValueError:
                                    continue
                            if value:
                                break
                        except:
                            continue
                if not value:
                    confidence = 0.0
            
            elif field_id == "venue":
                import re
                match = re.search(r'(?:venue|location|place)[:\s]+([^\n]{3,100})', all_text, re.I)
                if match:
                    value = match.group(1).strip()
                    confidence = 0.5
            
            elif field_id == "organizer":
                import re
                match = re.search(r'(?:organizer|organized by|department|school)[:\s]+([^\n]{3,100})', all_text, re.I)
                if match:
                    value = match.group(1).strip()
                    confidence = 0.5
            
            elif field_id == "participant_count":
                import re
                match = re.search(r'(?:participants?|attendees?|total|people)[:\s]*[:.]?\s*(\d+)', all_text, re.I)
                if match:
                    value = int(match.group(1))
                    confidence = 0.5
                else:
                    # Count rows in attendance data
                    count_match = re.search(r'(\d+)\s*(?:participants?|attendees?)', all_text, re.I)
                    if count_match:
                        value = int(count_match.group(1))
                        confidence = 0.4
            
            elif field_id == "objectives":
                import re
                # Look for list after "objective" keyword
                obj_match = re.search(r'(?:objective|aim|goal)s?[:\s]*(.+?)(?:\n\n|\Z)', all_text, re.S | re.I)
                if obj_match:
                    lines = [l.strip() for l in obj_match.group(1).split('\n') if l.strip()]
                    # Filter bullet points
                    objectives = [re.sub(r'^[\d\.\-\*]+', '', l).strip() for l in lines[:5] if len(l) > 10]
                    if objectives:
                        value = objectives
                        confidence = 0.4
            
            if value is not None:
                results.append(ExtractionResult(
                    field_id=field_id,
                    value=value,
                    confidence=confidence,
                    sources=[],
                ))
    
    return results
