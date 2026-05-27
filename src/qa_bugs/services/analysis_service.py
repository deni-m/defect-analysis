"""Analysis service - main orchestration logic."""
from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
from typing import Optional, Union, Dict
import pandas as pd

from qa_bugs.services.models import AnalysisConfig, AnalysisResult
from qa_bugs.services.kpi_calculator import calculate_summary_kpis
from qa_bugs.services.data_profiler import DataProfiler
from qa_bugs.ingest.normalizer import Normalizer
from qa_bugs.ingest.filters import apply_filters
from qa_bugs.metrics import METRICS
from qa_bugs.llm.service import LLMService


class AnalysisService:
    """
    Core analysis service - orchestrates the complete analysis workflow.

    This service is UI-agnostic and can be used by CLI, Streamlit, or API.
    It accepts a configuration and DataFrame, runs the analysis, and returns
    structured results.
    """

    def __init__(self, config: Union[AnalysisConfig, Dict]):
        """
        Initialize analysis service with configuration.

        Args:
            config: Either an AnalysisConfig object or a dict (legacy YAML format)
        """
        if isinstance(config, dict):
            self.config = AnalysisConfig.from_yaml_dict(config)
        else:
            self.config = config

    def run_analysis(
        self,
        df: pd.DataFrame,
        since: Optional[Union[str, date]] = None,
        until: Optional[Union[str, date]] = None,
        llm_enabled: Optional[bool] = None,
        log_dir: Optional[str] = None
    ) -> AnalysisResult:
        """
        Run complete analysis on the provided DataFrame.

        Workflow:
        1. Normalize CSV columns to canonical schema
        2. Apply date and status filters
        3. Compute enabled metrics
        4. Generate LLM insights (if enabled)
        5. Return structured results

        Args:
            df: Input DataFrame (raw CSV data)
            since: Optional start date filter (YYYY-MM-DD or date object)
            until: Optional end date filter (YYYY-MM-DD or date object)
            llm_enabled: Override LLM setting from config (None = use config)
            log_dir: Directory for LLM debug logs (None = no logging)

        Returns:
            AnalysisResult with all metric results and insights
        """
        # Convert date strings to date objects if needed
        since_date = self._parse_date(since) if since else None
        until_date = self._parse_date(until) if until else None

        # Step 1: Normalize DataFrame
        normalizer = Normalizer(
            mapping=self.config.fields_mapping,
            env_value_mapping=self.config.env_value_mapping
        )
        df_normalized = normalizer.normalize(df)

        # Step 1.5: Profile data for semantic understanding (if enabled)
        data_profile = None
        if self.config.auto_classification.enabled:
            # Initialize LLM service for profiling if needed
            llm_service = None
            should_use_llm = llm_enabled if llm_enabled is not None else self.config.llm.enabled
            if should_use_llm:
                llm_service = self._create_llm_service()
            
            profiler = DataProfiler(llm_service=llm_service)
            data_profile = profiler.profile_data(
                df_normalized,
                config=self.config.to_legacy_dict(),
                classify_statuses=self.config.auto_classification.classify_statuses,
                classify_priorities=self.config.auto_classification.classify_priorities,
                classify_environments=self.config.auto_classification.classify_environments
            )
            
            # Auto-apply classifications if confidence is high enough and manual review not required
            if not self.config.auto_classification.require_manual_review:
                self._apply_profile_to_config(data_profile)

        # Step 1.6: Validate required fields exist for enabled metrics
        missing_by_metric, warnings = self._validate_required_fields(df_normalized, self.config.enabled_metrics)
        if missing_by_metric:
            import logging
            logger = logging.getLogger(__name__)
            for mid, fields in missing_by_metric.items():
                logger.warning("Skipping metric '%s' — missing fields: %s", mid, fields)
        effective_metrics = [m for m in self.config.enabled_metrics if m not in missing_by_metric]

        # Log warnings for highly-recommended fields
        if warnings:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"\n{'='*70}\n"
                f"⚠️  MISSING HIGHLY RECOMMENDED FIELDS\n"
                f"{'='*70}\n"
                f"{warnings}\n"
                f"{'='*70}\n"
                f"Analysis will continue but results may be limited.\n"
            )

        # Step 2: Apply filters
        df_filtered = apply_filters(
            df_normalized,
            since=since_date.strftime("%Y-%m-%d") if since_date else None,
            until=until_date.strftime("%Y-%m-%d") if until_date else None,
            exclude_statuses=self.config.exclude_statuses
        )

        # For rejection_rate: apply date filters but not status filters
        df_date_filtered = apply_filters(
            df_normalized,
            since=since_date.strftime("%Y-%m-%d") if since_date else None,
            until=until_date.strftime("%Y-%m-%d") if until_date else None,
            exclude_statuses=[]  # Don't filter statuses for rejection_rate
        )

        # Step 3: Compute metrics
        # Note: rejection_rate needs date-filtered but not status-filtered data
        metrics_results = self._compute_metrics(df_filtered, df_unfiltered=df_date_filtered,
                                                profile=data_profile, enabled_metrics=effective_metrics)

        # Step 4: Generate LLM insights (if enabled)
        should_use_llm = llm_enabled if llm_enabled is not None else self.config.llm.enabled
        metric_insights = {}
        overall_summary = ""

        if should_use_llm:
            metric_insights, overall_summary = self._generate_insights(
                metrics_results,
                log_dir=log_dir
            )

        # Step 5: Calculate summary KPIs from metrics
        summary_kpis = calculate_summary_kpis(
            AnalysisResult(metrics_results=metrics_results)
        )
        # Display total defects as raw input row count (before status exclusions).
        summary_kpis.total_defects = int(len(df))

        # Step 6: Build result with metadata
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "total_records": len(df),
            "filtered_records": len(df_filtered),
            "since": since_date.isoformat() if since_date else None,
            "until": until_date.isoformat() if until_date else None,
            "llm_enabled": should_use_llm,
            "metrics_computed": list(metrics_results.keys()),
            "skipped_metrics": missing_by_metric,
        }

        return AnalysisResult(
            metrics_results=metrics_results,
            summary_kpis=summary_kpis,
            metric_insights=metric_insights,
            overall_summary=overall_summary,
            data_profile=data_profile,
            metadata=metadata
        )

    def _compute_metrics(self, df: pd.DataFrame, df_unfiltered: pd.DataFrame = None, profile: "DataProfile" = None, enabled_metrics: list[str] | None = None) -> Dict[str, "MetricResult"]:
        """
        Compute all enabled metrics.

        Args:
            df: Filtered and normalized DataFrame (for most metrics)
            df_unfiltered: Unfiltered normalized DataFrame (for metrics like rejection_rate that need all data)
            profile: Optional DataProfile with AI classifications

        Returns:
            Dictionary of metric_id -> MetricResult
        """
        results = {}
        metrics_params_root = self.config.metric_params
        common_params = metrics_params_root.get("common", {})

        # Get legacy dict for backward compatibility with metrics that need it
        legacy_config = self.config.to_legacy_dict()

        for metric_id in (enabled_metrics if enabled_metrics is not None else self.config.enabled_metrics):
            if metric_id not in METRICS:
                # Skip unknown metrics (could log warning here)
                continue

            metric_cls = METRICS[metric_id]
            specific_params = metrics_params_root.get(metric_id, {})

            # Merge common + specific params (specific overrides common)
            merged_params = {**common_params, **specific_params}

            # Provide fallback access to original full config for legacy metrics
            merged_params["__full_config__"] = legacy_config

            # Use unfiltered data for rejection_rate to count all rejected bugs (including cancelled)
            # Other metrics use filtered data to analyze valid bug lifecycle
            data_for_metric = df_unfiltered if (metric_id == "rejection_rate" and df_unfiltered is not None) else df

            # Compute metric - pass profile if metric supports it
            try:
                # Try calling with profile parameter (new signature)
                result = metric_cls().compute(data_for_metric, merged_params, profile=profile)
            except TypeError:
                # Fallback to old signature without profile (backward compatibility)
                result = metric_cls().compute(data_for_metric, merged_params)

            if getattr(result, "skip_report", False):
                continue

            results[metric_id] = result

        return results

    def _generate_insights(
        self,
        metrics_results: Dict[str, "MetricResult"],
        log_dir: Optional[str] = None
    ) -> tuple[Dict[str, str], str]:
        """
        Generate LLM insights for metrics.

        Args:
            metrics_results: Computed metric results
            log_dir: Optional directory for debug logs

        Returns:
            Tuple of (metric_insights dict, overall_summary)
        """
        # Convert LLM config back to dict format for LLMService
        llm_config_dict = {
            "enabled": self.config.llm.enabled,
            "prompts_dir": self.config.llm.prompts_dir,
            "provider": self.config.llm.provider,
            "endpoint": self.config.llm.endpoint,
            "deployment": self.config.llm.deployment,
            "api_version": self.config.llm.api_version,
            "temperature": self.config.llm.temperature,
            "max_tokens": self.config.llm.max_tokens,
            "debug": self.config.llm.debug,
            "log_prompts": self.config.llm.log_prompts,
            "table_row_limit": self.config.llm.table_row_limit,
            "summary_table_row_limit": self.config.llm.summary_table_row_limit,
            "max_prompt_chars": self.config.llm.max_prompt_chars,
            "context_format": self.config.llm.context_format
        }

        # Get legacy config for LLMService
        full_config = self.config.to_legacy_dict()

        # Initialize LLM service
        llm_service = LLMService(
            llm_config_dict,
            full_config=full_config,
            log_dir=log_dir or ""
        )

        # Generate insights per metric
        insights = {}
        for metric_id, result in metrics_results.items():
            if result.quality_notes:
                # Metric ran but results are unreliable — skip LLM, return plain explanation
                notes = " ".join(result.quality_notes)
                insights[metric_id] = f"⚠️ This metric could not be meaningfully calculated. {notes}"
                continue
            try:
                insight = llm_service.analyze_metric(metric_id, result.payload())
                insights[metric_id] = insight
            except Exception as e:
                # Log error but don't fail the whole analysis
                insights[metric_id] = f"Error generating insight: {str(e)}"

        # Generate overall summary
        try:
            overall = llm_service.summarize_texts(insights)
        except Exception as e:
            overall = f"Error generating summary: {str(e)}"

        return insights, overall

    def _validate_required_fields(self, df: pd.DataFrame, enabled_metrics: list[str]) -> tuple[dict[str, list[str]], Optional[str]]:
        """
        Validate that all required fields exist for enabled metrics.

        Args:
            df: Normalized DataFrame
            enabled_metrics: List of metric IDs to run

        Returns:
            Tuple of (missing_by_metric, warning_message)
            - missing_by_metric: Dict of {metric_id: [missing_field, ...]} for metrics that cannot run
            - warning_message: Warnings for highly-recommended fields
        """
        # Define required fields per metric
        # Note: resolved_at and priority are now MANDATORY for meaningful analysis
        METRIC_REQUIREMENTS = {
            "defect_age": {
                "required": ["created_at", "resolved_at"], 
                "highly_recommended": [],
                "impact_without": ""
            },
            "age_by_priority": {
                "required": ["created_at", "priority", "resolved_at"], 
                "highly_recommended": [],
                "impact_without": ""
            },
            "cumulative_open_closed": {
                "required": ["created_at", "resolved_at", "priority"], 
                "highly_recommended": [],
                "impact_without": ""
            },
            "leakage_rate": {
                "required": ["status", "environment", "priority"], 
                "highly_recommended": [],
                "impact_without": ""
            },
            "status_by_severity": {
                "required": ["status", "priority"], 
                "highly_recommended": [],
                "impact_without": ""
            },
            "rejection_rate": {
                "required": ["status"], 
                "highly_recommended": [],
                "impact_without": ""
            },
            "defects_by_env_priority": {
                "required": ["environment", "priority"], 
                "highly_recommended": [],
                "impact_without": ""
            },
            "defects_by_status_environment": {
                "required": ["environment", "status"],
                "highly_recommended": [],
                "impact_without": ""
            },
            "defects_by_priority": {
                "required": ["priority"],
                "highly_recommended": [],
                "impact_without": ""
            },
            "root_cause_distribution": {
                "required": ["root_cause"],
                "highly_recommended": [],
                "impact_without": ""
            },
        }
        
        available_cols = set(df.columns)
        missing_fields = {}
        missing_recommended = {}
        
        for metric_id in enabled_metrics:
            if metric_id not in METRIC_REQUIREMENTS:
                continue
                
            requirements = METRIC_REQUIREMENTS[metric_id]
            
            # Check required fields (blocking)
            required_fields = requirements["required"]
            missing = [field for field in required_fields if field not in available_cols]
            if missing:
                missing_fields[metric_id] = missing
            
            # Check highly recommended fields (warning only)
            recommended_fields = requirements.get("highly_recommended", [])
            missing_rec = [field for field in recommended_fields if field not in available_cols]
            if missing_rec:
                missing_recommended[metric_id] = {
                    "fields": missing_rec,
                    "impact": requirements.get("impact_without", "")
                }
        
        # Build warning message for highly recommended fields
        warning_msg = None
        if missing_recommended:
            warning_lines = []
            for metric_id, info in missing_recommended.items():
                metric_name = METRICS[metric_id].display_name if metric_id in METRICS else metric_id
                fields_str = ", ".join(info["fields"])
                impact_str = f"\n    Impact: {info['impact']}" if info['impact'] else ""
                warning_lines.append(f"  - {metric_name} ({metric_id}): missing {fields_str}{impact_str}")
            warning_msg = "\n".join(warning_lines)
        
        return missing_fields, warning_msg

    def check_metric_readiness(self, df: pd.DataFrame) -> dict[str, list[str]]:
        """Normalize df and return metrics that would be skipped due to missing fields."""
        normalizer = Normalizer(
            mapping=self.config.fields_mapping,
            env_value_mapping=self.config.env_value_mapping
        )
        df_normalized = normalizer.normalize(df)
        missing_by_metric, _ = self._validate_required_fields(df_normalized, self.config.enabled_metrics)
        return missing_by_metric

    @staticmethod
    def _parse_date(date_input: Union[str, date]) -> date:
        """Parse date from string or return date object as-is."""
        if isinstance(date_input, date):
            return date_input
        if isinstance(date_input, str):
            return datetime.strptime(date_input, "%Y-%m-%d").date()
        raise ValueError(f"Invalid date format: {date_input}")
    
    def _create_llm_service(self) -> "LLMService":
        """Create LLMService instance from config."""
        llm_config_dict = {
            "enabled": self.config.llm.enabled,
            "prompts_dir": self.config.llm.prompts_dir,
            "provider": self.config.llm.provider,
            "endpoint": self.config.llm.endpoint,
            "deployment": self.config.llm.deployment,
            "api_version": self.config.llm.api_version,
            "temperature": 0.1,  # Lower temperature for classification
            "max_tokens": 1000,
            "debug": self.config.llm.debug,
        }
        return LLMService(llm_config_dict)
    
    def _apply_profile_to_config(self, profile: "DataProfile") -> None:
        """Apply profile classifications to config if confidence is high enough."""
        threshold = self.config.auto_classification.confidence_threshold
        
        # Apply status classification
        if profile.status_profile and profile.status_profile.confidence >= threshold:
            import logging
            logger = logging.getLogger(__name__)
            # Guard against None lists if profiler returned nulls
            sp = profile.status_profile
            sp.open_statuses = sp.open_statuses or []
            sp.closed_statuses = sp.closed_statuses or []
            sp.rejected_statuses = sp.rejected_statuses or []
            logger.info(
                f"Auto-applying status classification (confidence: {sp.confidence:.0%}): "
                f"open={len(sp.open_statuses)}, "
                f"closed={len(sp.closed_statuses)}, "
                f"rejected={len(sp.rejected_statuses)}"
            )
            
            # Update metric params with classified statuses
            # This affects metrics that use open_statuses, rejected_statuses, etc.
            if "defect_age" in self.config.metric_params:
                self.config.metric_params["defect_age"]["open_statuses"] = sp.open_statuses
            
            if "status_by_severity" in self.config.metric_params:
                self.config.metric_params["status_by_severity"]["open_statuses"] = sp.open_statuses
                self.config.metric_params["status_by_severity"]["closed_statuses"] = sp.closed_statuses
            
            if "rejection_rate" in self.config.metric_params:
                self.config.metric_params["rejection_rate"]["rejected_statuses"] = sp.rejected_statuses
