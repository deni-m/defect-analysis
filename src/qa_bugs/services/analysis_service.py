"""Analysis service - main orchestration logic."""
from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
from typing import Optional, Union, Dict
import pandas as pd

from qa_bugs.services.models import AnalysisConfig, AnalysisResult
from qa_bugs.services.kpi_calculator import calculate_summary_kpis
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
        normalizer = Normalizer(mapping=self.config.fields_mapping)
        df_normalized = normalizer.normalize(df)

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
        metrics_results = self._compute_metrics(df_filtered, df_unfiltered=df_date_filtered)

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

        # Step 6: Build result with metadata
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "total_records": len(df),
            "filtered_records": len(df_filtered),
            "since": since_date.isoformat() if since_date else None,
            "until": until_date.isoformat() if until_date else None,
            "llm_enabled": should_use_llm,
            "metrics_computed": list(metrics_results.keys())
        }

        return AnalysisResult(
            metrics_results=metrics_results,
            summary_kpis=summary_kpis,
            metric_insights=metric_insights,
            overall_summary=overall_summary,
            metadata=metadata
        )

    def _compute_metrics(self, df: pd.DataFrame, df_unfiltered: pd.DataFrame = None) -> Dict[str, "MetricResult"]:
        """
        Compute all enabled metrics.

        Args:
            df: Filtered and normalized DataFrame (for most metrics)
            df_unfiltered: Unfiltered normalized DataFrame (for metrics like rejection_rate that need all data)

        Returns:
            Dictionary of metric_id -> MetricResult
        """
        results = {}
        metrics_params_root = self.config.metric_params
        common_params = metrics_params_root.get("common", {})

        # Get legacy dict for backward compatibility with metrics that need it
        legacy_config = self.config.to_legacy_dict()

        for metric_id in self.config.enabled_metrics:
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

            # Compute metric
            result = metric_cls().compute(data_for_metric, merged_params)
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

    @staticmethod
    def _parse_date(date_input: Union[str, date]) -> date:
        """Parse date from string or return date object as-is."""
        if isinstance(date_input, date):
            return date_input
        if isinstance(date_input, str):
            return datetime.strptime(date_input, "%Y-%m-%d").date()
        raise ValueError(f"Invalid date format: {date_input}")
