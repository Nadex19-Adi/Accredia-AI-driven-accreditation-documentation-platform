"""
Validation engine: validates extracted fields against template rules.
Rules are evaluated in code - never in LLM.
"""
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Callable
import re


class ValidationCheck:
    def __init__(self, rule_id: str, status: str, message: str, field_id: Optional[str] = None, details: dict = None):
        self.rule_id = rule_id
        self.field_id = field_id
        self.status = status  # ok, error, warning
        self.message = message
        self.details = details or {}


class RuleContext:
    """Context passed to rule evaluators"""
    def __init__(self, fields: Dict[str, Any], section_id: str):
        self.fields = fields
        self.section_id = section_id
        self._flat_fields = self._flatten_fields(fields)
    
    def get(self, field_id: str) -> Any:
        """Get field value from any section"""
        return self._flat_fields.get(field_id)
    
    def get_section(self, section_id: str) -> Dict[str, Any]:
        return self.fields.get(section_id, {})
    
    def _flatten_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        flat = {}
        for section_fields in fields.values():
            if isinstance(section_fields, dict):
                for fid, fdata in section_fields.items():
                    if isinstance(fdata, dict):
                        flat[fid] = fdata.get("value")
                    else:
                        flat[fid] = fdata
        return flat


class ValidationRule:
    """Base class for validation rules"""
    def __init__(self, rule_id: str, severity: str, message: str):
        self.rule_id = rule_id
        self.severity = severity
        self.message = message
    
    def evaluate(self, ctx: RuleContext) -> ValidationCheck:
        raise NotImplementedError


class RequiredFieldRule(ValidationRule):
    def __init__(self, rule_id: str, field_id: str, message: str, severity: str = "error"):
        super().__init__(rule_id, severity, message)
        self.field_id = field_id
    
    def evaluate(self, ctx: RuleContext) -> ValidationCheck:
        value = ctx.get(self.field_id)
        
        # Check if value is missing, None, or empty
        if value is None:
            return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id)
        
        if isinstance(value, str) and not value.strip():
            return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id)
        
        if isinstance(value, list) and len(value) == 0:
            return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id)
        
        return ValidationCheck(self.rule_id, "ok", f"{self.field_id} is present")


class DateRule(ValidationRule):
    """Rule: date <= today or date >= today"""
    def __init__(self, rule_id: str, field_id: str, operator: str, severity: str, message: str):
        super().__init__(rule_id, severity, message)
        self.field_id = field_id
        self.operator = operator  # <=, >=, ==, !=
    
    def evaluate(self, ctx: RuleContext) -> ValidationCheck:
        value = ctx.get(self.field_id)
        
        if value is None:
            return ValidationCheck(self.rule_id, "ok", "Skipped - no date")
        
        try:
            if isinstance(value, str):
                # Parse date
                for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%d/%m/%Y']:
                    try:
                        dt = datetime.strptime(value[:10], fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return ValidationCheck(self.rule_id, "warning", f"Could not parse date: {value}", self.field_id)
            else:
                dt = value
            
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            if self.operator == "<=":
                if dt <= today:
                    return ValidationCheck(self.rule_id, "ok", f"{self.field_id} date is valid")
                else:
                    return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id)
            
        except Exception as e:
            return ValidationCheck(self.rule_id, "warning", f"Date validation error: {e}", self.field_id)
        
        return ValidationCheck(self.rule_id, "ok", "Date check passed")


class RangeRule(ValidationRule):
    """Rule: field >= min or field <= max"""
    def __init__(self, rule_id: str, field_id: str, operator: str, threshold: float, severity: str, message: str):
        super().__init__(rule_id, severity, message)
        self.field_id = field_id
        self.operator = operator
        self.threshold = threshold
    
    def evaluate(self, ctx: RuleContext) -> ValidationCheck:
        value = ctx.get(self.field_id)
        
        if value is None:
            return ValidationCheck(self.rule_id, "ok", "Skipped - no value")
        
        try:
            num_value = float(value)
            
            if self.operator == ">=":
                if num_value >= self.threshold:
                    return ValidationCheck(self.rule_id, "ok", f"{self.field_id} >= {self.threshold}")
                else:
                    return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id, {"value": num_value, "threshold": self.threshold})
            
            elif self.operator == ">":
                if num_value > self.threshold:
                    return ValidationCheck(self.rule_id, "ok", f"{self.field_id} > {self.threshold}")
                else:
                    return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id, {"value": num_value, "threshold": self.threshold})
            
            elif self.operator == "<=":
                if num_value <= self.threshold:
                    return ValidationCheck(self.rule_id, "ok", f"{self.field_id} <= {self.threshold}")
                else:
                    return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id, {"value": num_value, "threshold": self.threshold})
        
        except (ValueError, TypeError):
            return ValidationCheck(self.rule_id, "warning", f"Cannot compare non-numeric value: {value}", self.field_id)
        
        return ValidationCheck(self.rule_id, "ok", "Range check passed")


class CollectionLengthRule(ValidationRule):
    """Rule: array.length >= min or array.length <= max"""
    def __init__(self, rule_id: str, field_id: str, min_len: Optional[int], max_len: Optional[int], severity: str, message: str):
        super().__init__(rule_id, severity, message)
        self.field_id = field_id
        self.min_len = min_len
        self.max_len = max_len
    
    def evaluate(self, ctx: RuleContext) -> ValidationCheck:
        value = ctx.get(self.field_id)
        
        if value is None:
            value = []
        
        if not isinstance(value, list):
            return ValidationCheck(self.rule_id, "warning", f"{self.field_id} is not a collection", self.field_id)
        
        length = len(value)
        
        if self.min_len is not None and length < self.min_len:
            return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id, {"count": length, "required": self.min_len})
        
        if self.max_len is not None and length > self.max_len:
            return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id, {"count": length, "max": self.max_len})
        
        return ValidationCheck(self.rule_id, "ok", f"{self.field_id} length is valid ({length})")


class TextMinItemsRule(ValidationRule):
    """Rule: text array has at least min_items"""
    def __init__(self, rule_id: str, field_id: str, min_items: int, severity: str, message: str):
        super().__init__(rule_id, severity, message)
        self.field_id = field_id
        self.min_items = min_items
    
    def evaluate(self, ctx: RuleContext) -> ValidationCheck:
        value = ctx.get(self.field_id)
        
        if value is None:
            if self.severity == "error":
                return ValidationCheck(self.rule_id, "error", self.message, self.field_id)
            return ValidationCheck(self.rule_id, "ok", "Skipped")
        
        if not isinstance(value, list):
            return ValidationCheck(self.rule_id, "warning", f"{self.field_id} should be a list", self.field_id)
        
        if len(value) < self.min_items:
            return ValidationCheck(self.rule_id, self.severity, self.message, self.field_id, {"count": len(value), "required": self.min_items})
        
        return ValidationCheck(self.rule_id, "ok", f"{self.field_id} has {len(value)} items")


def parse_date_comparison(rule: str) -> Optional[tuple]:
    """Parse rules like 'date <= today' or 'date >= today'"""
    match = re.match(r'(\w+)\s*(<=?|>=?|==|!=)\s*(today)', rule, re.I)
    if match:
        return (match.group(1), match.group(2), match.group(3))
    return None


def parse_range_rule(rule: str) -> Optional[tuple]:
    """Parse rules like 'participant_count >= 0'"""
    match = re.match(r'(\w+)\s*(>=?|<=?)\s*(-?\d+\.?\d*)', rule, re.I)
    if match:
        return (match.group(1), match.group(2), float(match.group(3)))
    return None


def parse_collection_rule(rule: str) -> Optional[tuple]:
    """Parse rules like 'photos.length >= 2'"""
    match = re.match(r'(\w+)\.length\s*(>=?|<=?)\s*(\d+)', rule, re.I)
    if match:
        return (match.group(1), match.group(2), int(match.group(3)))
    return None


def build_rules_from_schema(schema: Dict[str, Any]) -> List[ValidationRule]:
    """Build validation rules from template schema"""
    rules = []
    
    # Add required field rules from schema
    for section in schema.get("sections", []):
        for field in section.get("fields", []):
            if field.get("required"):
                field_id = field["id"]
                label = field.get("label", field_id)
                rules.append(RequiredFieldRule(
                    rule_id=f"required_{field_id}",
                    field_id=field_id,
                    message=f"'{label}' is required",
                ))
                
                # Add min items rule for arrays
                if field.get("type", "").endswith("[]"):
                    min_items = field.get("min_items", 1)
                    rules.append(TextMinItemsRule(
                        rule_id=f"min_items_{field_id}",
                        field_id=field_id,
                        min_items=min_items,
                        severity="error" if field.get("required") else "warning",
                        message=f"At least {min_items} item(s) required for '{label}'",
                    ))
    
    # Parse explicit validation rules
    for rule_def in schema.get("validation_rules", []):
        rule_id = rule_def["id"]
        rule_expr = rule_def["rule"]
        severity = rule_def.get("severity", "error")
        message = rule_def.get("message", f"Validation failed for rule {rule_id}")
        
        # Try to parse as date rule
        date_parts = parse_date_comparison(rule_expr)
        if date_parts:
            rules.append(DateRule(
                rule_id=rule_id,
                field_id=date_parts[0],
                operator=date_parts[1],
                severity=severity,
                message=message,
            ))
            continue
        
        # Try to parse as range rule
        range_parts = parse_range_rule(rule_expr)
        if range_parts:
            rules.append(RangeRule(
                rule_id=rule_id,
                field_id=range_parts[0],
                operator=range_parts[1],
                threshold=range_parts[2],
                severity=severity,
                message=message,
            ))
            continue
        
        # Try to parse as collection length rule
        coll_parts = parse_collection_rule(rule_expr)
        if coll_parts:
            op = coll_parts[1]
            threshold = coll_parts[2]
            if op == ">=":
                rules.append(CollectionLengthRule(
                    rule_id=rule_id,
                    field_id=coll_parts[0],
                    min_len=threshold,
                    max_len=None,
                    severity=severity,
                    message=message,
                ))
            continue
    
    return rules


def validate_fields(schema: Dict[str, Any], extracted_fields: Dict[str, Dict[str, Any]]) -> List[ValidationCheck]:
    """
    Main validation function.
    extracted_fields: {section_id: {field_id: {"value": ..., "status": ...}}}
    """
    # Convert to rule context format
    rule_context = RuleContext(extracted_fields, "")
    
    rules = build_rules_from_schema(schema)
    results = []
    
    for rule in rules:
        check = rule.evaluate(rule_context)
        results.append(check)
    
    return results