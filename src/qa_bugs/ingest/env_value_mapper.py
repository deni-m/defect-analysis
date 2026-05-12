"""Environment value mapping service with LLM-based auto-detection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set
import logging
import re
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentMappingResult:
    """Result of environment value mapping."""
    success: bool
    value_mapping: Dict[str, str]  # original_value -> canonical_value
    errors: List[str]
    warnings: List[str]
    unique_values: List[str]
    method_used: str  # "llm", "fuzzy", or "passthrough"


class EnvironmentValueMapper:
    """
    Service for auto-detecting and mapping environment values to standard categories.
    
    Analyzes unique environment values in data and maps them to standard categories:
    - LOCAL, DEV, QA, STAGE, UAT, PERF, PROD
    
    Supports:
    - LLM-based intelligent classification
    - Fuzzy keyword matching fallback
    - Configurable target categories
    """
    
    # Standard environment categories in typical pipeline order
    DEFAULT_CATEGORIES = ["LOCAL", "DEV", "QA", "STAGE", "UAT", "PERF", "PROD"]
    
    # Fuzzy matching keywords for each category
    CATEGORY_KEYWORDS = {
        "LOCAL": ["local", "localhost", "dev-local", "development-local"],
        "DEV": ["dev", "develop", "development", "int", "integration", "dev-"],
        "QA": ["qa", "test", "testing", "tst", "quality", "verification"],
        "STAGE": ["stage", "staging", "stg", "pre-prod", "preprod"],
        "UAT": ["uat", "acceptance", "user-acceptance", "pre-production"],
        "PERF": ["perf", "performance", "load", "stress"],
        "PROD": ["prod", "production", "prd", "live", "release"],
    }
    
    def __init__(self, llm_service: Optional["LLMService"] = None, target_categories: Optional[List[str]] = None):
        """
        Initialize environment value mapper.
        
        Args:
            llm_service: LLMService instance for intelligent classification (if None, uses fuzzy matching)
            target_categories: List of target environment categories (defaults to DEFAULT_CATEGORIES)
        """
        self.llm_service = llm_service
        self.llm_enabled = llm_service is not None and llm_service.enabled
        self.target_categories = target_categories or self.DEFAULT_CATEGORIES
    
    # Minimum fill rate below which environment mapping is skipped (sparse/unreliable field)
    MIN_FILL_RATE = 0.05

    def auto_map_values(
        self,
        unique_values: List[str],
        allow_passthrough: bool = True,
        total_rows: Optional[int] = None,
        filled_rows: Optional[int] = None,
    ) -> EnvironmentMappingResult:
        """
        Auto-map environment values to standard categories.

        Args:
            unique_values: List of unique environment values from data
            allow_passthrough: If True, unmapped values stay as-is; if False, they're flagged as errors
            total_rows: Total number of rows in the dataset (for fill-rate check)
            filled_rows: Number of rows with a non-null environment value (for fill-rate check)

        Returns:
            EnvironmentMappingResult with mapping and validation status
        """
        # Filter out empty/null values
        unique_values = [v for v in unique_values if v and str(v).strip() and str(v).upper() != "NAN"]

        if not unique_values:
            logger.warning("No unique environment values to map")
            return EnvironmentMappingResult(
                success=True,
                value_mapping={},
                errors=[],
                warnings=["No environment values found in data"],
                unique_values=[],
                method_used="passthrough"
            )

        # Fill-rate guard: skip mapping if the environment field is almost empty
        if total_rows and filled_rows is not None:
            fill_rate = filled_rows / total_rows
            if fill_rate < self.MIN_FILL_RATE:
                msg = (
                    f"Environment field fill rate is only {fill_rate:.1%} "
                    f"({filled_rows}/{total_rows} rows). "
                    "Skipping environment mapping — field is too sparse to be reliable."
                )
                logger.warning(msg)
                return EnvironmentMappingResult(
                    success=True,
                    value_mapping={},
                    errors=[],
                    warnings=[msg],
                    unique_values=unique_values,
                    method_used="passthrough"
                )

        # Separate valid-looking env values from garbage (multi-line, version strings, etc.)
        valid_values = [v for v in unique_values if self._is_valid_env_value(v)]
        invalid_values = [v for v in unique_values if not self._is_valid_env_value(v)]

        if invalid_values:
            logger.warning(
                "Skipping %d value(s) that do not look like environment names (will be kept as-is): %s",
                len(invalid_values), invalid_values
            )

        logger.info(f"Auto-mapping {len(valid_values)} valid environment values: {valid_values}")

        if not valid_values:
            # All values were garbage — passthrough everything
            warning = (
                "All environment values appear to be non-environment data "
                f"(e.g. device/version strings): {invalid_values}. Values kept as-is."
            )
            return EnvironmentMappingResult(
                success=True,
                value_mapping={v: str(v).upper() for v in unique_values},
                errors=[],
                warnings=[warning],
                unique_values=unique_values,
                method_used="passthrough"
            )

        # Try LLM-based mapping first (only on valid values)
        if self.llm_enabled and self.llm_service:
            logger.info("LLM service enabled, attempting LLM-based environment value mapping")
            result = self._llm_map_values(valid_values, allow_passthrough)
        else:
            logger.info("LLM service not available, using fuzzy keyword matching")
            result = self._fuzzy_map_values(valid_values, allow_passthrough)

        # Merge passthrough mappings for invalid values
        for v in invalid_values:
            result.value_mapping[v] = str(v).upper()
            result.warnings.append(
                f"Value '{v}' does not look like an environment name — kept as-is."
            )
        result.unique_values = unique_values
        return result

    @staticmethod
    def _is_valid_env_value(value: str) -> bool:
        """
        Return False for values that clearly are not environment names.

        Rejects:
        - Multi-line values (contain \\n or \\r)
        - Values longer than 60 characters
        - Version/device patterns like "iOS 571 Android 541" (word+digits repeated)
        """
        s = str(value).strip()
        if "\n" in s or "\r" in s:
            return False
        if len(s) > 60:
            return False
        # Reject patterns like "Word 123 Word 456" — looks like device/version info
        if re.search(r'\b[A-Za-z]+\s+\d+\s+[A-Za-z]+\s+\d+', s):
            return False
        return True
    
    def _llm_map_values(
        self,
        unique_values: List[str],
        allow_passthrough: bool
    ) -> EnvironmentMappingResult:
        """Use LLM to intelligently map environment values to standard categories."""
        logger.info(f"Attempting LLM-based environment mapping for values: {unique_values}")
        
        # Build prompt
        prompt = self._build_mapping_prompt(unique_values)
        logger.debug(f"LLM prompt:\n{prompt}")
        
        try:
            # Call LLM
            messages = [{"role": "user", "content": prompt}]
            logger.debug(f"Sending prompt to LLM (length: {len(prompt)} chars)")
            
            ok, response_text, error = self.llm_service._chat(
                model=self.llm_service.deployment,
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
                metric_id="env_value_mapping"
            )
            
            if not ok:
                logger.warning(f"LLM call failed: {error}. Falling back to fuzzy matching")
                return self._fuzzy_map_values(unique_values, allow_passthrough, llm_error=error)
            
            logger.info("LLM call successful, parsing response")
            logger.debug(f"LLM response:\n{response_text}")
            
            # Parse response
            value_mapping = self._parse_llm_response(response_text)
            logger.info(f"LLM mapped {len(value_mapping)} environment values")
            logger.debug(f"LLM mapping: {value_mapping}")
            
            # Validate and build result
            return self._build_result(value_mapping, unique_values, allow_passthrough, "llm")
            
        except Exception as e:
            logger.error(f"Exception during LLM environment mapping: {e}. Falling back to fuzzy matching", exc_info=True)
            return self._fuzzy_map_values(unique_values, allow_passthrough, llm_error=str(e))
    
    def _fuzzy_map_values(
        self,
        unique_values: List[str],
        allow_passthrough: bool,
        llm_error: Optional[str] = None
    ) -> EnvironmentMappingResult:
        """Fallback fuzzy keyword matching for environment values."""
        if llm_error:
            logger.info(f"Starting fuzzy matching fallback (reason: {llm_error})")
        else:
            logger.info("Starting fuzzy keyword matching for environment values")
        
        value_mapping = {}
        
        for value in unique_values:
            value_lower = str(value).lower().strip()
            matched = False
            
            # Try exact match with target categories first
            if value.upper() in self.target_categories:
                value_mapping[value] = value.upper()
                matched = True
                logger.debug(f"Exact match: {value} -> {value.upper()}")
                continue
            
            # Try keyword matching
            for category, keywords in self.CATEGORY_KEYWORDS.items():
                if category not in self.target_categories:
                    continue
                    
                for keyword in keywords:
                    if keyword in value_lower:
                        value_mapping[value] = category
                        matched = True
                        logger.debug(f"Keyword match: {value} -> {category} (keyword: {keyword})")
                        break
                
                if matched:
                    break
            
            # If no match and passthrough allowed, keep original (uppercased)
            if not matched and allow_passthrough:
                value_mapping[value] = value.upper()
                logger.debug(f"No match, passthrough: {value} -> {value.upper()}")
        
        result = self._build_result(value_mapping, unique_values, allow_passthrough, "fuzzy")
        
        # Add LLM error as warning if present
        if llm_error:
            result.warnings.insert(0, f"LLM mapping failed ({llm_error}), used fuzzy keyword matching")
        
        return result
    
    def _build_result(
        self,
        value_mapping: Dict[str, str],
        unique_values: List[str],
        allow_passthrough: bool,
        method: str
    ) -> EnvironmentMappingResult:
        """Build EnvironmentMappingResult with validation."""
        errors = []
        warnings = []
        
        # Check for unmapped values
        unmapped = [v for v in unique_values if v not in value_mapping]
        
        if unmapped:
            if allow_passthrough:
                warnings.append(f"Unmapped environment values (kept as-is): {', '.join(unmapped)}")
                # Add passthrough mappings
                for v in unmapped:
                    value_mapping[v] = v.upper()
            else:
                errors.append(f"Failed to map environment values: {', '.join(unmapped)}")
        
        # Check for new categories not in target list
        new_categories = set(value_mapping.values()) - set(self.target_categories)
        if new_categories:
            warnings.append(
                f"Mapping introduced new categories not in config: {', '.join(sorted(new_categories))}. "
                f"These will be included in analysis (data-driven approach)."
            )
        
        success = len(errors) == 0
        
        return EnvironmentMappingResult(
            success=success,
            value_mapping=value_mapping,
            errors=errors,
            warnings=warnings,
            unique_values=unique_values,
            method_used=method
        )
    
    def _build_mapping_prompt(self, unique_values: List[str]) -> str:
        """Build prompt for LLM environment value mapping."""
        values_str = "\n".join([f"  - {v}" for v in unique_values])
        categories_str = ", ".join(self.target_categories)
        
        prompt_template = """You are a DevOps environment classification assistant. Given a list of environment values from a bug tracking system, map each value to a standard environment category.

**Standard Environment Categories (in typical pipeline order):**
{categories}

**Classification Rules:**
1. PROD/PRODUCTION: Production, live, release environments
2. UAT: User acceptance testing, pre-production
3. PERF: Performance, load testing environments  
4. STAGE/STAGING: Staging, pre-prod environments
5. QA/TEST: Quality assurance, testing, verification environments
6. DEV: Development, integration environments
7. LOCAL: Local development, localhost

**Analysis Guidelines:**
- Look for keywords in environment names (e.g., "prod" → PROD, "testing" → QA)
- Consider common naming patterns (e.g., "app-staging" → STAGE, "dev-server" → DEV)
- If a value clearly matches a category, map it
- If uncertain, use the closest logical match
- If value is already a standard category name, keep it
- Be case-insensitive in analysis

**Task:**
Analyze the following environment values and map each to the most appropriate standard category.

**Environment Values to Map:**
{values}

**Response Format:**
Return ONLY a YAML mapping in this exact format (no markdown fences, no explanations):

value_mapping:
  "original_value_1": CATEGORY
  "original_value_2": CATEGORY
  ...

Use EXACT original values (case-sensitive) as keys. Use UPPERCASE category names as values.

Example:
value_mapping:
  "Production": PROD
  "qa-server": QA
  "dev-env": DEV
  "staging-1": STAGE

Your response (YAML only):"""
        
        return prompt_template.format(
            categories=categories_str,
            values=values_str
        )
    
    def _parse_llm_response(self, response: str) -> Dict[str, str]:
        """Parse YAML mapping from LLM response."""
        import yaml
        
        # Extract YAML from potential markdown fences
        if "```yaml" in response:
            response = response.split("```yaml")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        # Parse YAML
        data = yaml.safe_load(response)
        
        if "value_mapping" in data:
            return data["value_mapping"]
        else:
            # If LLM returned just the mapping dict without wrapper
            return data
    
    def format_result_message(self, result: EnvironmentMappingResult) -> str:
        """Format mapping result as user-friendly message."""
        if not result.success:
            msg_parts = ["❌ Environment Value Mapping Failed\n"]
            
            if result.errors:
                msg_parts.append("**Errors:**")
                for error in result.errors:
                    msg_parts.append(f"  • {error}")
                msg_parts.append("")
            
            return "\n".join(msg_parts)
        
        msg_parts = [f"✓ Environment value mapping successful ({result.method_used})\n"]
        
        if result.value_mapping:
            msg_parts.append("**Mappings Applied:**")
            for orig, mapped in sorted(result.value_mapping.items()):
                if orig.upper() != mapped:  # Only show actual transformations
                    msg_parts.append(f"  • {orig} → {mapped}")
            msg_parts.append("")
        
        if result.warnings:
            msg_parts.append("**Warnings:**")
            for warning in result.warnings:
                msg_parts.append(f"  • {warning}")
            msg_parts.append("")
        
        return "\n".join(msg_parts)
