"""Environment value mapping service with LLM-based auto-detection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
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
    # Debug info
    llm_prompt: Optional[str] = None
    llm_raw_response: Optional[str] = None
    llm_error: Optional[str] = None


class EnvironmentValueMapper:
    """
    Service for auto-detecting and mapping environment values to standard categories.
    
    Analyzes unique environment values in data and maps them to standard categories:
    - LOCAL, DEV, QA, STAGE, UAT, PERF, PROD, NON_PROD
    
    Supports:
    - LLM-based intelligent classification
    - Fuzzy keyword matching fallback
    - Configurable target categories
    """
    
    # Standard environment categories in typical pipeline order
    DEFAULT_CATEGORIES = ["LOCAL", "DEV", "QA", "STAGE", "UAT", "PERF", "PROD", "NON_PROD"]
    
    # Conservative aliases. Values not matching these exact aliases are preserved.
    EXACT_ALIASES = {
        "local": "LOCAL",
        "localhost": "LOCAL",
        "dev": "DEV",
        "develop": "DEV",
        "development": "DEV",
        "qa": "QA",
        "test": "QA",
        "testing": "QA",
        "tst": "QA",
        "stage": "STAGE",
        "staging": "STAGE",
        "stg": "STAGE",
        "uat": "UAT",
        "acceptance": "UAT",
        "perf": "PERF",
        "performance": "PERF",
        "prod": "PROD",
        "production": "PROD",
        "prd": "PROD",
        "live": "PROD",
        "non_prod": "NON_PROD",
        "nonprod": "NON_PROD",
        "non_production": "NON_PROD",
        "nonproduction": "NON_PROD",
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
    # Maximum number of unique valid-looking values before treating field as free-text
    MAX_UNIQUE_ENV_VALUES = 10

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

        # High-cardinality guard: if too many distinct valid-looking values remain, the
        # Environment field is likely free-text (not a structured env picker) — skip mapping.
        if len(valid_values) > self.MAX_UNIQUE_ENV_VALUES:
            msg = (
                f"Environment field has {len(valid_values)} unique values after filtering "
                f"(threshold: {self.MAX_UNIQUE_ENV_VALUES}). "
                "The field appears to be free-text rather than a structured environment selector. "
                "Skipping environment mapping — values kept as-is."
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
        - URLs (contain http:// or https://)
        - UUIDs (hex-dash pattern)
        - Values containing colons (e.g. "ENV: TAC ML", image markup)
        - Values containing 3+ comma-separated tokens (free-text lists)
        - Values containing image/markup syntax (!image- or |width=)
        """
        s = str(value).strip()
        if "\n" in s or "\r" in s:
            return False
        if len(s) > 60:
            return False
        # Reject URLs
        if re.search(r'https?://', s, re.IGNORECASE):
            return False
        # Reject UUIDs (e.g. "8f7644ba-6951-4ce0-892e-9f366b0c24b2")
        if re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', s, re.IGNORECASE):
            return False
        # Reject values containing colons ("ENV: TAC ML", image markup dimensions)
        if ":" in s:
            return False
        # Reject image/markup syntax
        if re.search(r'!image-|\|width=|\|height=|alt="', s, re.IGNORECASE):
            return False
        # Reject free-text lists: 3 or more comma-separated tokens
        if s.count(",") >= 2:
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
                result = self._fuzzy_map_values(unique_values, allow_passthrough, llm_error=error)
                result.llm_prompt = prompt
                result.llm_error = error
                return result
            
            logger.info("LLM call successful, parsing response")
            logger.debug(f"LLM response:\n{response_text}")
            
            # Parse response
            value_mapping = self._parse_llm_response(response_text)
            logger.info(f"LLM mapped {len(value_mapping)} environment values")
            logger.debug(f"LLM mapping: {value_mapping}")
            
            # Validate and build result
            result = self._build_result(value_mapping, unique_values, allow_passthrough, "llm")
            result.llm_prompt = prompt
            result.llm_raw_response = response_text
            return result
            
        except Exception as e:
            logger.error(f"Exception during LLM environment mapping: {e}. Falling back to fuzzy matching", exc_info=True)
            result = self._fuzzy_map_values(unique_values, allow_passthrough, llm_error=str(e))
            result.llm_prompt = prompt
            result.llm_error = str(e)
            return result
    
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
            mapped_value, confidence, reason = self._classify_env_value(value)
            if mapped_value in self.target_categories:
                value_mapping[value] = mapped_value
                logger.debug(
                    "Environment classification: %s -> %s (confidence=%.2f, reason=%s)",
                    value, mapped_value, confidence, reason
                )
                continue

            if allow_passthrough:
                value_mapping[value] = self._preserve_env_value(value)
                logger.debug(
                    "Environment passthrough: %s -> %s (confidence=%.2f, reason=%s)",
                    value, value_mapping[value], confidence, reason
                )
        
        result = self._build_result(value_mapping, unique_values, allow_passthrough, "fuzzy")
        
        # Add LLM error as warning if present
        if llm_error:
            result.warnings.insert(0, f"LLM mapping failed ({llm_error}), used fuzzy keyword matching")
        
        return result

    @staticmethod
    def _normalize_env_value(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value).lower().strip()).strip("_")

    @staticmethod
    def _preserve_env_value(value: str) -> str:
        return str(value).strip().upper()

    def _classify_env_value(self, value: str) -> Tuple[str, float, str]:
        normalized_value = self._normalize_env_value(value)

        if not normalized_value:
            return self._preserve_env_value(value), 0.0, "empty value"

        exact_category = normalized_value.upper()
        if exact_category in self.target_categories:
            return exact_category, 1.0, "already a target category"

        alias_category = self.EXACT_ALIASES.get(normalized_value)
        if alias_category:
            return alias_category, 1.0, "exact alias"

        return self._preserve_env_value(value), 0.0, "preserved original value"
    
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
    
    @staticmethod
    def _sanitize_for_prompt(value: str) -> str:
        """Remove/replace characters that cause LLM XML parsers to fail (e.g. cp1252 smart quotes)."""
        # Replace Windows-1252 special chars (U+0080–U+009F) with ASCII equivalents
        replacements = {
            "\u0091": "'", "\u0092": "'", "\u0093": '"', "\u0094": '"',
            "\u0096": "-", "\u0097": "-", "\u0085": "...",
        }
        for bad, good in replacements.items():
            value = value.replace(bad, good)
        # Strip remaining control characters (U+0000–U+001F and U+007F–U+009F)
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', value)
        return value

    def _build_mapping_prompt(self, unique_values: List[str]) -> str:
        """Build prompt for LLM environment value mapping."""
        sanitized = [self._sanitize_for_prompt(v) for v in unique_values]
        values_str = "\n".join([f"  - {v}" for v in sanitized])
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
8. NON_PROD: Broad non-production labels that do not identify a specific stage

**Analysis Guidelines:**
- Look for keywords in environment names (e.g., "prod" → PROD, "testing" → QA)
- Consider common naming patterns (e.g., "app-staging" → STAGE, "dev-server" → DEV)
- If a value clearly matches a specific category, map it
- If a value is broad like "Non-Prod" or "Non-Production", map it to NON_PROD, not DEV
- If uncertain, keep the original value uppercased instead of forcing it into DEV/QA/PROD
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

        # Sanitize the response before YAML parsing — LLM may echo back values
        # containing control characters that break the YAML scanner.
        response = self._sanitize_for_prompt(response)

        # Parse YAML
        data = yaml.safe_load(response)

        if not isinstance(data, dict):
            raise ValueError(f"LLM response did not parse to a dict: {type(data)}")

        if "value_mapping" in data:
            return {str(k): str(v) for k, v in data["value_mapping"].items()}
        else:
            # If LLM returned just the mapping dict without wrapper
            return {str(k): str(v) for k, v in data.items()}
    
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
