"""Field mapping service with LLM-based auto-detection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import re
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class MappingValidationResult:
    """Result of field mapping validation."""
    valid: bool
    mapping: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    missing_required: List[str]
    missing_optional: List[str]
    # Debug info
    method_used: str = ""
    llm_prompt: Optional[str] = None
    llm_raw_response: Optional[str] = None
    llm_error: Optional[str] = None


@dataclass
class EnvironmentColumnCandidate:
    """Profile of a possible environment column."""
    column: str
    filled_rows: int
    fill_rate: float
    unique_count: int
    unique_values: List[str]
    score: float
    reasons: List[str]


@dataclass
class ResolutionColumnCandidate:
    """Profile of a possible resolution outcome column."""
    column: str
    filled_rows: int
    fill_rate: float
    unique_count: int
    unique_values: List[str]
    score: float
    reasons: List[str]


@dataclass
class RootCauseColumnCandidate:
    """Profile of a possible root cause column."""
    column: str
    filled_rows: int
    fill_rate: float
    unique_count: int
    unique_values: List[str]
    score: float
    reasons: List[str]


class FieldMappingService:
    """
    Service for detecting and validating field mappings.
    
    Supports:
    - LLM-based auto-detection (via existing LLMService)
    - Fuzzy matching fallback
    - Manual mapping validation
    """
    
    REQUIRED_FIELDS = ["key", "created_at", "status", "priority"]
    OPTIONAL_FIELDS = ["resolved_at", "resolution", "environment", "fix_version", "root_cause"]
    MAX_ENV_UNIQUE_VALUES = 25
    MAX_RESOLUTION_UNIQUE_VALUES = 30
    ENV_VALUE_HINTS = {
        "local", "localhost",
        "dev", "development",
        "qa", "test", "testing",
        "stage", "staging",
        "uat", "sit", "int", "integration",
        "perf", "performance",
        "preprod", "pre_prod", "pre-production", "preproduction",
        "prod", "production",
        "sandbox",
    }
    RESOLUTION_VALUE_HINTS = {
        "accepted": {
            "fixed", "done", "resolved", "completed", "deployed",
            "released", "closed", "verified", "implemented",
        },
        "rejected": {
            "rejected", "canceled", "cancelled", "wontfix", "won_t_fix",
            "won_t_do", "wontdo", "duplicate", "invalid",
            "cannot_reproduce", "can_t_reproduce", "not_a_bug",
            "out_of_scope", "by_design",
        },
        "other": {
            "unresolved", "open", "none", "empty", "not_set", "no_resolution",
        },
    }
    
    # Fallback fuzzy matching synonyms
    FIELD_SYNONYMS = {
        "key": ["id", "bug_id", "defect_id", "issue_id", "key", "ticket", "issue_key"],
        "created_at": ["created", "created_at", "creation_date", "opened", "open_date", "created_date"],
        "resolved_at": ["resolved", "resolved_at", "closed", "closed_date", "resolution_date", "resolved_date"],
        "status": ["status", "state", "issue_status"],
        "resolution": ["resolution", "resolve", "resolution_status"],
        "priority": ["priority", "severity", "importance", "prio", "priority_level"],
        "environment": ["environment", "env", "target_env", "test_env", "deployment_env"],
        "fix_version": ["fix_version", "target_version", "fixed_in", "version", "release"],
        "root_cause": [
            "root_cause", "root cause", "rootcause", "rca", "cause",
            "cause_category", "defect_cause", "bug_cause", "failure_cause",
            "reason_category", "root_cause_category",
        ],
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
                result = self._fuzzy_detect_mapping(df, error=error)
                result.llm_prompt = prompt
                result.llm_error = error
                return result
            
            logger.info("LLM call successful, parsing response")
            logger.debug(f"LLM response:\n{response_text}")
            
            # Parse YAML response
            mapping = self._parse_llm_response(response_text)
            resolution_warnings = self._apply_resolution_candidate_mapping(mapping, df)
            env_warnings = self._apply_environment_candidate_mapping(mapping, df)
            root_cause_warnings = self._apply_root_cause_candidate_mapping(mapping, df)
            logger.info(f"LLM detected mapping for {len(mapping)} fields")
            logger.debug(f"Detected mapping: {mapping}")
            
            # Validate mapping
            result = self.validate_mapping(mapping, df)
            result.warnings.extend(resolution_warnings)
            result.warnings.extend(env_warnings)
            result.warnings.extend(root_cause_warnings)

            # Supplement LLM mapping with fuzzy matches for any optional fields
            # the LLM may have missed, then re-validate.
            fuzzy_supplements = self._fuzzy_supplement(mapping, df)
            if fuzzy_supplements:
                logger.info(f"Fuzzy supplement added {len(fuzzy_supplements)} optional fields: {list(fuzzy_supplements.keys())}")
                mapping.update(fuzzy_supplements)
                resolution_warnings = self._apply_resolution_candidate_mapping(mapping, df)
                env_warnings = self._apply_environment_candidate_mapping(mapping, df)
                root_cause_warnings = self._apply_root_cause_candidate_mapping(mapping, df)
                result = self.validate_mapping(mapping, df)
                result.warnings.extend(resolution_warnings)
                result.warnings.extend(env_warnings)
                result.warnings.extend(root_cause_warnings)

            result.method_used = "llm"
            result.llm_prompt = prompt
            result.llm_raw_response = response_text
            logger.info(f"LLM mapping validation: valid={result.valid}, errors={len(result.errors)}, warnings={len(result.warnings)}")
            return result
            
        except Exception as e:
            logger.error(f"Exception during LLM mapping: {e}. Falling back to fuzzy matching", exc_info=True)
            result = self._fuzzy_detect_mapping(df, error=str(e))
            result.llm_prompt = prompt
            result.llm_error = str(e)
            return result
    
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
            if canonical == "environment":
                continue
            if canonical == "resolution":
                continue
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
        
        resolution_warnings = self._apply_resolution_candidate_mapping(mapping, df)
        env_warnings = self._apply_environment_candidate_mapping(mapping, df)
        root_cause_warnings = self._apply_root_cause_candidate_mapping(mapping, df)
        logger.info(f"Fuzzy matching completed, detected {len(mapping)} field mappings")
        
        result = self.validate_mapping(mapping, df)
        result.warnings.extend(resolution_warnings)
        result.warnings.extend(env_warnings)
        result.warnings.extend(root_cause_warnings)
        result.method_used = "fuzzy"

        # Add LLM error as warning if present
        if error:
            result.warnings.insert(0, f"LLM detection failed ({error}), used fuzzy matching")
            result.llm_error = error
        
        logger.info(f"Fuzzy mapping validation: valid={result.valid}, errors={len(result.errors)}, warnings={len(result.warnings)}")
        return result

    def _fuzzy_supplement(self, existing_mapping: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
        """Fuzzy-match optional fields not yet in existing_mapping.
        Returns only new canonical → column entries (does not override existing ones)."""
        from difflib import SequenceMatcher

        already_mapped_cols = {
            col
            for mapped in existing_mapping.values()
            for col in (mapped if isinstance(mapped, list) else [mapped])
        }
        columns_lower = {col.lower().strip(): col for col in df.columns}
        supplements = {}

        for canonical in self.OPTIONAL_FIELDS:
            if canonical == "environment":
                continue
            if canonical == "resolution":
                continue
            if canonical == "root_cause":
                continue
            if canonical in existing_mapping:
                continue  # already mapped by LLM
            synonyms = self.FIELD_SYNONYMS.get(canonical, [canonical])
            best_match, best_score = None, 0.6
            for col_lower, col_orig in columns_lower.items():
                if col_orig in already_mapped_cols:
                    continue  # column already claimed
                for synonym in synonyms:
                    score = SequenceMatcher(None, col_lower, synonym.lower()).ratio()
                    if score > best_score:
                        best_score = score
                        best_match = col_orig
            if best_match:
                supplements[canonical] = best_match

        return supplements

    def _apply_environment_candidate_mapping(self, mapping: Dict[str, Any], df: pd.DataFrame) -> List[str]:
        """Choose a single best environment column based on name and value profile."""
        previous = mapping.get("environment")
        excluded_columns = {
            col
            for field, mapped in mapping.items()
            if field != "environment"
            for col in (mapped if isinstance(mapped, list) else [mapped])
        }
        candidates = self._profile_environment_candidates(df, excluded_columns)

        if not candidates:
            if "environment" in mapping:
                del mapping["environment"]
                return [
                    "Environment mapping ignored because no non-empty, low-cardinality "
                    "environment-like column was found"
                ]
            return []

        best = candidates[0]
        mapping["environment"] = best.column
        logger.info(
            "Selected environment column '%s' (score=%.2f, filled=%s, unique=%s, values=%s)",
            best.column,
            best.score,
            best.filled_rows,
            best.unique_count,
            best.unique_values[:8],
        )

        warnings = []
        if previous and previous != best.column:
            warnings.append(
                f"Environment column '{best.column}' selected by value profile instead of '{previous}'"
            )

        if len(candidates) > 1 and candidates[0].score - candidates[1].score <= 0.75:
            second = candidates[1]
            warnings.append(
                "Multiple possible environment columns found; selected "
                f"'{best.column}' (unique={best.unique_count}, values={best.unique_values[:5]}) "
                f"over '{second.column}' (unique={second.unique_count}, values={second.unique_values[:5]})"
            )

        return warnings

    def _apply_resolution_candidate_mapping(self, mapping: Dict[str, Any], df: pd.DataFrame) -> List[str]:
        """Choose a single best resolution outcome column based on name and values."""
        previous = mapping.get("resolution")
        excluded_columns = {
            col
            for field, mapped in mapping.items()
            if field != "resolution"
            for col in (mapped if isinstance(mapped, list) else [mapped])
        }
        candidates = self._profile_resolution_candidates(df, excluded_columns)

        if not candidates:
            if "resolution" in mapping:
                del mapping["resolution"]
                return [
                    "Resolution mapping ignored because no non-empty, low-cardinality "
                    "resolution outcome column was found"
                ]
            return []

        best = candidates[0]
        mapping["resolution"] = best.column
        logger.info(
            "Selected resolution column '%s' (score=%.2f, filled=%s, unique=%s, values=%s)",
            best.column,
            best.score,
            best.filled_rows,
            best.unique_count,
            best.unique_values[:8],
        )

        warnings = []
        if previous and previous != best.column:
            warnings.append(
                f"Resolution column '{best.column}' selected by value profile instead of '{previous}'"
            )

        if len(candidates) > 1 and candidates[0].score - candidates[1].score <= 0.75:
            second = candidates[1]
            warnings.append(
                "Multiple possible resolution columns found; selected "
                f"'{best.column}' (unique={best.unique_count}, values={best.unique_values[:5]}) "
                f"over '{second.column}' (unique={second.unique_count}, values={second.unique_values[:5]})"
            )

        return warnings

    def _apply_root_cause_candidate_mapping(self, mapping: Dict[str, Any], df: pd.DataFrame) -> List[str]:
        """Choose a single best root cause column based on name and non-empty values."""
        previous = mapping.get("root_cause")
        excluded_columns = {
            col
            for field, mapped in mapping.items()
            if field != "root_cause"
            for col in (mapped if isinstance(mapped, list) else [mapped])
        }
        candidates = self._profile_root_cause_candidates(df, excluded_columns)

        if not candidates:
            if "root_cause" in mapping:
                del mapping["root_cause"]
                return [
                    "Root cause mapping ignored because no non-empty root-cause-like column was found"
                ]
            return []

        best = candidates[0]
        mapping["root_cause"] = best.column
        logger.info(
            "Selected root cause column '%s' (score=%.2f, filled=%s, unique=%s, values=%s)",
            best.column,
            best.score,
            best.filled_rows,
            best.unique_count,
            best.unique_values[:8],
        )

        warnings = []
        if previous and previous != best.column:
            warnings.append(
                f"Root cause column '{best.column}' selected by value profile instead of '{previous}'"
            )
        if len(candidates) > 1 and candidates[0].score - candidates[1].score <= 0.75:
            second = candidates[1]
            warnings.append(
                "Multiple possible root cause columns found; selected "
                f"'{best.column}' (filled={best.filled_rows}, unique={best.unique_count}) "
                f"over '{second.column}' (filled={second.filled_rows}, unique={second.unique_count})"
            )
        return warnings

    def _profile_root_cause_candidates(
        self,
        df: pd.DataFrame,
        excluded_columns: set[str],
    ) -> List[RootCauseColumnCandidate]:
        candidates = []

        for column in df.columns:
            if column in excluded_columns:
                continue

            values = self._clean_candidate_values(df[column])
            filled_rows = int(values.notna().sum())
            if filled_rows == 0:
                continue

            if self._series_looks_date_like(values):
                continue

            unique_values = values.dropna().value_counts().index.astype(str).tolist()
            unique_count = len(unique_values)
            if unique_count == 0:
                continue

            name_score, name_reasons = self._root_cause_name_score(column)
            if name_score == 0:
                continue

            fill_rate = filled_rows / len(df) if len(df) else 0
            avg_len = float(values.dropna().astype(str).str.len().mean())
            long_text_penalty = 0.75 if avg_len > 120 else 0
            cardinality_penalty = 0.5 if unique_count > max(20, filled_rows * 0.8) else 0
            score = name_score + (fill_rate * 2) - long_text_penalty - cardinality_penalty

            reasons = [*name_reasons]
            reasons.append(f"{unique_count} unique values")
            reasons.append(f"{fill_rate:.0%} filled")

            candidates.append(RootCauseColumnCandidate(
                column=column,
                filled_rows=filled_rows,
                fill_rate=fill_rate,
                unique_count=unique_count,
                unique_values=unique_values[:10],
                score=score,
                reasons=reasons,
            ))

        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)

    def _profile_resolution_candidates(
        self,
        df: pd.DataFrame,
        excluded_columns: set[str],
    ) -> List[ResolutionColumnCandidate]:
        candidates = []

        for column in df.columns:
            if column in excluded_columns:
                continue

            values = self._clean_candidate_values(df[column])
            filled_rows = int(values.notna().sum())
            if filled_rows == 0:
                continue

            if self._series_looks_date_like(values):
                continue

            unique_values = values.dropna().value_counts().index.astype(str).tolist()
            unique_count = len(unique_values)
            if unique_count == 0 or unique_count > self.MAX_RESOLUTION_UNIQUE_VALUES:
                continue

            avg_len = float(values.dropna().astype(str).str.len().mean())
            if avg_len > 80:
                continue

            name_score, name_reasons = self._resolution_name_score(column)
            outcome_like_count = sum(self._looks_like_resolution_value(value) for value in values.dropna())
            outcome_value_ratio = outcome_like_count / filled_rows

            if name_score == 0 and outcome_value_ratio < 0.35:
                continue

            fill_rate = filled_rows / len(df) if len(df) else 0
            cardinality_score = max(0, 1 - (unique_count / self.MAX_RESOLUTION_UNIQUE_VALUES))
            long_text_penalty = 1.5 if avg_len > 30 else 0
            score = (
                name_score
                + (outcome_value_ratio * 4)
                + (fill_rate * 1.5)
                + cardinality_score
                - long_text_penalty
            )

            reasons = [*name_reasons]
            if outcome_value_ratio >= 0.35:
                reasons.append(f"{outcome_value_ratio:.0%} resolution-like values")
            reasons.append(f"{unique_count} unique values")
            reasons.append(f"{fill_rate:.0%} filled")

            candidates.append(ResolutionColumnCandidate(
                column=column,
                filled_rows=filled_rows,
                fill_rate=fill_rate,
                unique_count=unique_count,
                unique_values=unique_values[:10],
                score=score,
                reasons=reasons,
            ))

        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)

    def _profile_environment_candidates(
        self,
        df: pd.DataFrame,
        excluded_columns: set[str],
    ) -> List[EnvironmentColumnCandidate]:
        candidates = []

        for column in df.columns:
            if column in excluded_columns:
                continue

            values = self._clean_candidate_values(df[column])
            filled_rows = int(values.notna().sum())
            if filled_rows == 0:
                continue

            unique_values = values.dropna().value_counts().index.astype(str).tolist()
            unique_count = len(unique_values)
            if unique_count == 0 or unique_count > self.MAX_ENV_UNIQUE_VALUES:
                continue

            avg_len = float(values.dropna().astype(str).str.len().mean())
            if avg_len > 80:
                continue

            name_score, name_reasons = self._environment_name_score(column)
            env_like_count = sum(self._looks_like_environment_value(value) for value in values.dropna())
            env_value_ratio = env_like_count / filled_rows

            if name_score == 0 and env_value_ratio < 0.35:
                continue

            fill_rate = filled_rows / len(df) if len(df) else 0
            cardinality_score = max(0, 1 - (unique_count / self.MAX_ENV_UNIQUE_VALUES))
            long_text_penalty = 1.5 if avg_len > 30 else 0
            score = (
                name_score
                + (env_value_ratio * 4)
                + (fill_rate * 1.5)
                + cardinality_score
                - long_text_penalty
            )

            reasons = [*name_reasons]
            if env_value_ratio >= 0.35:
                reasons.append(f"{env_value_ratio:.0%} environment-like values")
            reasons.append(f"{unique_count} unique values")
            reasons.append(f"{fill_rate:.0%} filled")

            candidates.append(EnvironmentColumnCandidate(
                column=column,
                filled_rows=filled_rows,
                fill_rate=fill_rate,
                unique_count=unique_count,
                unique_values=unique_values[:10],
                score=score,
                reasons=reasons,
            ))

        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)

    @staticmethod
    def _clean_candidate_values(series: pd.Series) -> pd.Series:
        values = series.astype("string").str.strip()
        return values.replace("", pd.NA)

    def _environment_name_score(self, column: str) -> tuple[float, List[str]]:
        normalized = self._normalize_column_label(column)
        base = re.sub(r"_\d+$", "", normalized)
        tokens = set(base.split("_"))
        reasons = []

        if base == "environment":
            return 3.0, ["exact environment name"]
        if "environment" in tokens or base.endswith("_environment") or base.startswith("environment_"):
            reasons.append("environment in column name")
            return 2.25, reasons
        if "env" in tokens:
            reasons.append("env in column name")
            return 1.75, reasons
        if {"target", "test", "deployment"} & tokens and {"server", "system", "instance"} & tokens:
            reasons.append("deployment-like column name")
            return 0.75, reasons
        return 0, reasons

    def _resolution_name_score(self, column: str) -> tuple[float, List[str]]:
        normalized = self._normalize_column_label(column)
        tokens = set(normalized.split("_"))
        reasons = []

        if normalized == "resolution":
            return 3.0, ["exact resolution name"]
        if "resolution" in tokens and not ({"date", "time"} & tokens):
            reasons.append("resolution in column name")
            return 2.25, reasons
        if {"reason", "outcome", "disposition"} & tokens and {"close", "closure", "resolution"} & tokens:
            reasons.append("resolution outcome-like column name")
            return 1.75, reasons
        if normalized in {"close_reason", "closure_reason", "defect_outcome"}:
            reasons.append("resolution outcome-like column name")
            return 1.75, reasons
        return 0, reasons

    def _root_cause_name_score(self, column: str) -> tuple[float, List[str]]:
        normalized = self._normalize_column_label(column)
        tokens = set(normalized.split("_"))
        reasons = []

        if normalized in {"root_cause", "rootcause"}:
            return 3.0, ["exact root cause name"]
        if normalized == "rca":
            return 2.75, ["RCA column name"]
        if "rca" in tokens:
            reasons.append("RCA in column name")
            return 2.25, reasons
        if {"root", "cause"} <= tokens:
            reasons.append("root cause in column name")
            return 2.5, reasons
        if "cause" in tokens and {"category", "type", "group", "reason"} & tokens:
            reasons.append("cause category-like column name")
            return 2.0, reasons
        if {"defect", "bug", "failure", "issue"} & tokens and "cause" in tokens:
            reasons.append("defect cause-like column name")
            return 1.75, reasons
        if normalized in {"cause", "cause_category", "reason_category", "failure_cause"}:
            reasons.append("cause-like column name")
            return 1.5, reasons
        return 0, reasons

    def _looks_like_environment_value(self, value: Any) -> bool:
        normalized = self._normalize_column_label(str(value))
        if normalized in self.ENV_VALUE_HINTS:
            return True
        tokens = set(normalized.split("_"))
        return bool(tokens & self.ENV_VALUE_HINTS)

    def _looks_like_resolution_value(self, value: Any) -> bool:
        normalized = self._normalize_column_label(str(value))
        all_hints = set().union(*self.RESOLUTION_VALUE_HINTS.values())
        if normalized in all_hints:
            return True
        tokens = set(normalized.split("_"))
        return bool(tokens & all_hints)

    @staticmethod
    def _series_looks_date_like(values: pd.Series) -> bool:
        filled = values.dropna()
        if filled.empty:
            return False
        candidate_text = filled.astype(str)
        has_date_pattern = candidate_text.str.contains(
            r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}",
            regex=True,
            na=False,
        )
        if has_date_pattern.mean() < 0.5:
            return False
        parsed = pd.to_datetime(filled, errors="coerce", utc=True)
        return bool(parsed.notna().mean() >= 0.8)

    @staticmethod
    def _normalize_column_label(value: str) -> str:
        value = re.sub(r"\.\d+$", "", value.lower().strip())
        return re.sub(r"[^a-z0-9]+", "_", value).strip("_")

    def validate_mapping(
        self,
        mapping: Dict[str, Any],
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
            elif not self._mapping_columns_exist(mapping[field], df):
                errors.append(
                    f"Mapped column '{mapping[field]}' for field '{field}' "
                    f"does not exist in CSV"
                )
        
        # Check optional fields — only warn if a plausible candidate column exists in the CSV
        # but wasn't mapped. Silently skip if the CSV simply doesn't have that kind of data.
        df_cols_lower = {c.lower().replace(" ", "_").replace("/", "_") for c in df.columns}
        for field in self.OPTIONAL_FIELDS:
            if field not in mapping:
                synonyms = {s.lower() for s in self.FIELD_SYNONYMS.get(field, [field])}
                has_candidate = bool(synonyms & df_cols_lower)
                if has_candidate:
                    missing_optional.append(field)
                    warnings.append(f"Optional field '{field}' not mapped (analysis may be limited)")
            elif not self._mapping_columns_exist(mapping[field], df):
                warnings.append(
                    f"Mapped column '{mapping[field]}' for field '{field}' "
                    f"does not exist in CSV (will be ignored)"
                )
                # Remove invalid optional mapping
                del mapping[field]
        
        # Check for duplicate mappings
        column_usage = {}
        for field, column in mapping.items():
            usage_key = tuple(column) if isinstance(column, list) else column
            if usage_key in column_usage:
                warnings.append(
                    f"Column '{column}' mapped to multiple fields: "
                    f"{column_usage[usage_key]} and {field}"
                )
            column_usage[usage_key] = field
        
        valid = len(missing_required) == 0 and len(errors) == 0
        
        return MappingValidationResult(
            valid=valid,
            mapping=mapping,
            errors=errors,
            warnings=warnings,
            missing_required=missing_required,
            missing_optional=missing_optional
        )

    @staticmethod
    def _mapping_columns_exist(mapped_columns: Any, df: pd.DataFrame) -> bool:
        columns = mapped_columns if isinstance(mapped_columns, list) else [mapped_columns]
        return all(column in df.columns for column in columns)
    
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
- resolution: resolution/outcome of the bug (e.g., Fixed, Won't Fix, Cancelled, Duplicate)
- environment: deployment environment (DEV, QA, PROD, UAT, etc.)
- fix_version: target fix version or release
- root_cause: root cause, RCA, or cause category explaining why the defect occurred

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
  resolution: <column_name>   # omit if not found
  environment: <column_name>  # omit if not found
  fix_version: <column_name>  # omit if not found
  root_cause: <column_name>   # omit if not found or empty
```

**Rules:**
- ALL REQUIRED fields (key, created_at, status, priority) MUST be mapped ONLY if suitable columns exist
- If you cannot find a column with appropriate data for a required field, OMIT it - validation will fail anyway
- Only include mappings you're confident about (>90% certainty based on BOTH name AND data)
- Use exact column names from the CSV (case-sensitive)
- If multiple columns look related to environment, choose only the one whose values most resemble deployment environments
- If a root cause / RCA-like column exists but is empty, omit it
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
