"""Field mapping service with LLM-based auto-detection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import logging
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class MappingValidationResult:
    """Result of field mapping validation."""
    valid: bool
    mapping: Dict[str, str]
    errors: List[str]
    warnings: List[str]
    missing_required: List[str]
    missing_optional: List[str]


class FieldMappingService:
    """
    Service for detecting and validating field mappings.
    
    Supports:
    - LLM-based auto-detection (via existing LLMService)
    - Fuzzy matching fallback
    - Manual mapping validation
    """
    
    REQUIRED_FIELDS = ["key", "created_at", "status", "priority"]
    OPTIONAL_FIELDS = ["resolved_at", "environment", "fix_version"]
    
    # Fallback fuzzy matching synonyms
    FIELD_SYNONYMS = {
        "key": ["id", "bug_id", "defect_id", "issue_id", "key", "ticket", "issue_key"],
        "created_at": ["created", "created_at", "creation_date", "opened", "open_date", "created_date"],
        "resolved_at": ["resolved", "resolved_at", "closed", "closed_date", "resolution_date", "resolved_date"],
        "status": ["status", "state", "resolution", "issue_status"],
        "priority": ["priority", "severity", "importance", "prio", "priority_level"],
        "environment": ["environment", "env", "target_env", "test_env", "deployment_env"],
        "fix_version": ["fix_version", "target_version", "fixed_in", "version", "release"],
    }
    
    def __init__(self, llm_service: Optional["LLMService"] = None):
        """
        Initialize field mapping service.
        
        Args:
            llm_service: Existing LLMService instance (if None, uses fuzzy matching only)
        """
        self.llm_service = llm_service
        self.llm_enabled = llm_service is not None and llm_service.enabled
    
    def auto_detect_mapping(
        self,
        df: pd.DataFrame,
        sample_rows: int = 5
    ) -> MappingValidationResult:
        """
        Auto-detect field mapping using LLM or fuzzy matching.
        
        Args:
            df: Input DataFrame
            sample_rows: Number of sample rows to analyze
        
        Returns:
            MappingValidationResult with detected mapping and validation status
        """
        logger.info(f"Auto-detecting field mapping for {len(df.columns)} columns, {len(df)} rows")
        
        if self.llm_enabled and self.llm_service:
            logger.info("LLM service is enabled, attempting LLM-based detection")
            return self._llm_detect_mapping(df, sample_rows)
        else:
            logger.info("LLM service not available, using fuzzy matching only")
            return self._fuzzy_detect_mapping(df)
    
    def _llm_detect_mapping(
        self,
        df: pd.DataFrame,
        sample_rows: int = 5
    ) -> MappingValidationResult:
        """Use LLM to detect field mapping."""
        logger.info(f"Attempting LLM-based field mapping with {sample_rows} sample rows")
        
        # Prepare CSV sample for LLM
        csv_sample = self._format_csv_sample(df, sample_rows)
        
        # Build prompt
        prompt = self._build_mapping_prompt(csv_sample)
        logger.debug(f"LLM prompt:\n{prompt}")
        
        try:
            # Call LLM via existing service
            messages = [{"role": "user", "content": prompt}]
            logger.debug(f"Sending prompt to LLM (length: {len(prompt)} chars)")
            
            ok, response_text, error = self.llm_service._chat(
                model=self.llm_service.deployment,
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
                metric_id="field_mapping"
            )
            
            if not ok:
                logger.warning(f"LLM call failed: {error}. Falling back to fuzzy matching")
                return self._fuzzy_detect_mapping(df, error=error)
            
            logger.info("LLM call successful, parsing response")
            logger.debug(f"LLM response:\n{response_text}")
            
            # Parse YAML response
            mapping = self._parse_llm_response(response_text)
            logger.info(f"LLM detected mapping for {len(mapping)} fields")
            logger.debug(f"Detected mapping: {mapping}")
            
            # Validate mapping
            result = self.validate_mapping(mapping, df)
            logger.info(f"LLM mapping validation: valid={result.valid}, errors={len(result.errors)}, warnings={len(result.warnings)}")
            return result
            
        except Exception as e:
            logger.error(f"Exception during LLM mapping: {e}. Falling back to fuzzy matching", exc_info=True)
            return self._fuzzy_detect_mapping(df, error=str(e))
    
    def _fuzzy_detect_mapping(
        self,
        df: pd.DataFrame,
        error: Optional[str] = None
    ) -> MappingValidationResult:
        """Fallback fuzzy matching for field detection."""
        if error:
            logger.info(f"Starting fuzzy matching fallback (reason: {error})")
        else:
            logger.info("Starting fuzzy matching detection")
        
        from difflib import SequenceMatcher
        
        columns_lower = {col.lower().strip(): col for col in df.columns}
        mapping = {}
        
        for canonical, synonyms in self.FIELD_SYNONYMS.items():
            best_match = None
            best_score = 0.6  # minimum threshold
            
            for col_lower, col_orig in columns_lower.items():
                for synonym in synonyms:
                    score = SequenceMatcher(None, col_lower, synonym.lower()).ratio()
                    if score > best_score:
                        best_score = score
                        best_match = col_orig
            
            if best_match:
                mapping[canonical] = best_match
                logger.debug(f"Fuzzy match: {canonical} -> {best_match} (score: {best_score:.2f})")
        
        logger.info(f"Fuzzy matching completed, detected {len(mapping)} field mappings")
        
        result = self.validate_mapping(mapping, df)
        
        # Add LLM error as warning if present
        if error:
            result.warnings.insert(0, f"LLM detection failed ({error}), used fuzzy matching")
        
        logger.info(f"Fuzzy mapping validation: valid={result.valid}, errors={len(result.errors)}, warnings={len(result.warnings)}")
        return result
    
    def validate_mapping(
        self,
        mapping: Dict[str, str],
        df: pd.DataFrame
    ) -> MappingValidationResult:
        """
        Validate that mapping contains all required fields and columns exist.
        
        Args:
            mapping: Dictionary of canonical_field -> csv_column
            df: Input DataFrame to validate against
        
        Returns:
            MappingValidationResult with validation status and errors
        """
        errors = []
        warnings = []
        missing_required = []
        missing_optional = []
        
        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in mapping:
                missing_required.append(field)
                errors.append(f"Required field '{field}' not mapped")
            elif mapping[field] not in df.columns:
                errors.append(
                    f"Mapped column '{mapping[field]}' for field '{field}' "
                    f"does not exist in CSV"
                )
        
        # Check optional fields
        for field in self.OPTIONAL_FIELDS:
            if field not in mapping:
                missing_optional.append(field)
                warnings.append(f"Optional field '{field}' not mapped (analysis may be limited)")
            elif mapping[field] not in df.columns:
                warnings.append(
                    f"Mapped column '{mapping[field]}' for field '{field}' "
                    f"does not exist in CSV (will be ignored)"
                )
                # Remove invalid optional mapping
                del mapping[field]
        
        # Check for duplicate mappings
        column_usage = {}
        for field, column in mapping.items():
            if column in column_usage:
                warnings.append(
                    f"Column '{column}' mapped to multiple fields: "
                    f"{column_usage[column]} and {field}"
                )
            column_usage[column] = field
        
        valid = len(missing_required) == 0 and len(errors) == 0
        
        return MappingValidationResult(
            valid=valid,
            mapping=mapping,
            errors=errors,
            warnings=warnings,
            missing_required=missing_required,
            missing_optional=missing_optional
        )
    
    def _format_csv_sample(self, df: pd.DataFrame, rows: int) -> str:
        """Format DataFrame sample for LLM prompt."""
        sample = df.head(rows)
        csv_str = f"Columns: {', '.join(df.columns)}\n\n"
        csv_str += "Sample rows:\n"
        csv_str += sample.to_string(index=False, max_colwidth=50)
        return csv_str
    
    def _build_mapping_prompt(self, csv_sample: str) -> str:
        """Build prompt for LLM field mapping."""
        prompt_template = """You are a data mapping assistant. Given CSV column headers and sample data, suggest which columns map to our canonical field names.

**Canonical fields (REQUIRED - must be mapped):**
- key: unique bug/defect identifier (e.g., JIRA-123, BUG-456)
- created_at: timestamp when bug was created (must contain date/time values)
- status: current bug state (e.g., Open, Closed, Resolved, In Progress)
- priority: bug priority level (e.g., High, Medium, Low, Critical)

**Canonical fields (OPTIONAL - map if available):**
- resolved_at: timestamp when bug was resolved/closed (must contain date/time values)
- environment: deployment environment (DEV, QA, PROD, UAT, etc.)
- fix_version: target fix version or release

**CRITICAL VALIDATION RULES:**
1. **Look at the DATA, not just column names** - verify sample values match the expected field type
2. For date fields (created_at, resolved_at): column MUST contain actual date/timestamp values (ISO format, YYYY-MM-DD, etc.)
3. For created_at: if no column contains date values, you CANNOT map it - this will fail validation
4. For status: column should contain state names (Open, Closed, etc.), not random text
5. For priority: column should contain priority levels (High, Low, etc.), not other data
6. NEVER map a column based only on position or guessing - verify the actual data

**Task:**
Analyze the provided CSV columns and sample rows. Return ONLY valid YAML mapping in this exact format:

```yaml
fields_mapping:
  key: <column_name>
  created_at: <column_name>
  status: <column_name>
  priority: <column_name>
  resolved_at: <column_name>  # omit if not found
  environment: <column_name>  # omit if not found
  fix_version: <column_name>  # omit if not found
```

**Rules:**
- ALL REQUIRED fields (key, created_at, status, priority) MUST be mapped ONLY if suitable columns exist
- If you cannot find a column with appropriate data for a required field, OMIT it - validation will fail anyway
- Only include mappings you're confident about (>90% certainty based on BOTH name AND data)
- Use exact column names from the CSV (case-sensitive)
- If a canonical field has no clear match with correct data type, omit it from the output
- Return ONLY the YAML block, no explanation or markdown fences

**CSV Data:**
{csv_sample}

Your response (YAML only):"""
        
        return prompt_template.format(csv_sample=csv_sample)
    
    def _parse_llm_response(self, response: str) -> Dict[str, str]:
        """Parse YAML mapping from LLM response."""
        # Extract YAML from potential markdown fences
        if "```yaml" in response:
            response = response.split("```yaml")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        # Parse YAML
        data = yaml.safe_load(response)
        
        if "fields_mapping" in data:
            return data["fields_mapping"]
        else:
            # If LLM returned just the mapping dict without wrapper
            return data
    
    def format_validation_error(self, result: MappingValidationResult) -> str:
        """Format validation result as user-friendly error message."""
        if result.valid:
            return "✓ All required fields mapped successfully"
        
        msg_parts = ["❌ Field Mapping Validation Failed\n"]
        
        if result.errors:
            msg_parts.append("**Errors:**")
            for error in result.errors:
                msg_parts.append(f"  • {error}")
            msg_parts.append("")
        
        if result.missing_required:
            msg_parts.append("**Missing Required Fields:**")
            msg_parts.append(f"  {', '.join(result.missing_required)}")
            msg_parts.append("")
            msg_parts.append("**Action Required:**")
            msg_parts.append("  1. Check your CSV file has these columns")
            msg_parts.append("  2. Or manually configure field mapping in config file")
            msg_parts.append("")
        
        if result.warnings:
            msg_parts.append("**Warnings:**")
            for warning in result.warnings:
                msg_parts.append(f"  • {warning}")
        
        return "\n".join(msg_parts)
