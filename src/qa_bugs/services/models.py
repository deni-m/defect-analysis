"""Data models for analysis service layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from qa_bugs.metrics.base import MetricResult

if TYPE_CHECKING:
    from qa_bugs.services.kpi_calculator import SummaryKPIs
    from qa_bugs.services.data_profiler import DataProfile


@dataclass
class AutoMappingConfig:
    """Configuration for automatic field mapping."""
    enabled: bool = False
    sample_rows: int = 5


@dataclass
class AutoEnvMappingConfig:
    """Configuration for automatic environment value mapping."""
    enabled: bool = False
    allow_passthrough: bool = True
    target_categories: List[str] = field(default_factory=lambda: ["LOCAL", "DEV", "QA", "STAGE", "UAT", "PERF", "PROD", "NON_PROD"])


@dataclass
class AutoClassificationConfig:
    """Configuration for automatic status/priority/environment classification."""
    enabled: bool = False
    classify_statuses: bool = True
    classify_priorities: bool = True
    classify_environments: bool = True
    require_manual_review: bool = False  # If True, show classification but don't auto-apply
    confidence_threshold: float = 0.6  # Minimum confidence to auto-apply


@dataclass
class LLMConfig:
    """Configuration for LLM integration."""
    enabled: bool = True
    prompts_dir: str = "prompts"  # Path relative to qa_bugs package directory
    provider: str = "azure"
    endpoint: Optional[str] = None
    deployment: str = "gpt-5.4"
    api_version: str = "2024-05-01-preview"
    temperature: float = 1.0
    max_tokens: int = 700
    debug: bool = False
    log_prompts: bool = False
    table_row_limit: int = 200
    summary_table_row_limit: int = 40
    max_prompt_chars: int = 120000
    context_format: str = "csv"


@dataclass
class ProjectConfig:
    """Project-level configuration."""
    timezone: str = "UTC"
    name: Optional[str] = None
    version: Optional[str] = None


@dataclass
class AnalysisConfig:
    """
    Complete analysis configuration.

    This can be constructed from YAML config dict or created programmatically.
    Serves as the input contract for AnalysisService.
    """
    # Project settings
    project: ProjectConfig = field(default_factory=ProjectConfig)

    # Field mappings from CSV to canonical schema
    fields_mapping: Dict[str, Any] = field(default_factory=dict)

    # Automatic field mapping configuration
    auto_mapping: AutoMappingConfig = field(default_factory=AutoMappingConfig)

    # Automatic environment value mapping configuration
    auto_env_mapping: AutoEnvMappingConfig = field(default_factory=AutoEnvMappingConfig)

    # Manual environment value mapping (applied before auto-mapping)
    env_value_mapping: Dict[str, str] = field(default_factory=dict)

    # Automatic semantic classification configuration
    auto_classification: AutoClassificationConfig = field(default_factory=AutoClassificationConfig)

    # Metrics configuration
    enabled_metrics: List[str] = field(default_factory=list)
    metric_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Filters
    exclude_statuses: List[str] = field(default_factory=list)

    # LLM configuration
    llm: LLMConfig = field(default_factory=LLMConfig)

    @classmethod
    def from_yaml_dict(cls, config_dict: Dict[str, Any]) -> AnalysisConfig:
        """
        Create AnalysisConfig from YAML config dictionary.

        Args:
            config_dict: Dictionary loaded from YAML config file

        Returns:
            AnalysisConfig instance
        """
        # Extract project config
        project_dict = config_dict.get("project", {})
        project = ProjectConfig(
            timezone=project_dict.get("timezone", "UTC"),
            name=project_dict.get("name"),
            version=project_dict.get("version")
        )

        # Extract fields mapping
        fields_mapping = config_dict.get("fields_mapping", {})

        # Extract auto_mapping config
        auto_mapping_dict = config_dict.get("auto_mapping", {})
        auto_mapping = AutoMappingConfig(
            enabled=auto_mapping_dict.get("enabled", False),
            sample_rows=auto_mapping_dict.get("sample_rows", 5)
        )

        # Extract auto_env_mapping config
        auto_env_mapping_dict = config_dict.get("auto_env_mapping", {})
        auto_env_mapping = AutoEnvMappingConfig(
            enabled=auto_env_mapping_dict.get("enabled", False),
            allow_passthrough=auto_env_mapping_dict.get("allow_passthrough", True),
            target_categories=auto_env_mapping_dict.get("target_categories", ["LOCAL", "DEV", "QA", "STAGE", "UAT", "PERF", "PROD", "NON_PROD"])
        )

        # Extract manual environment value mapping
        env_value_mapping = config_dict.get("env_value_mapping", {})

        # Extract auto_classification config
        auto_classification_dict = config_dict.get("auto_classification", {})
        auto_classification = AutoClassificationConfig(
            enabled=auto_classification_dict.get("enabled", False),
            classify_statuses=auto_classification_dict.get("classify_statuses", True),
            classify_priorities=auto_classification_dict.get("classify_priorities", True),
            classify_environments=auto_classification_dict.get("classify_environments", True),
            require_manual_review=auto_classification_dict.get("require_manual_review", False),
            confidence_threshold=auto_classification_dict.get("confidence_threshold", 0.6)
        )

        # Extract metrics configuration
        metrics_config = config_dict.get("metrics", {})
        enabled_metrics = metrics_config.get("enabled", [])
        metric_params = metrics_config.get("params", {})

        # Extract exclude_statuses (might be in common params or root level)
        exclude_statuses = config_dict.get("exclude_statuses", [])
        if not exclude_statuses and "common" in metric_params:
            exclude_statuses = metric_params.get("common", {}).get("exclude_statuses", [])

        # Extract LLM config
        llm_dict = config_dict.get("llm", {})
        llm_config = LLMConfig(
            enabled=llm_dict.get("enabled", True),
            prompts_dir=llm_dict.get("prompts_dir", "qa_bugs/prompts"),
            provider=llm_dict.get("provider", "azure"),
            endpoint=llm_dict.get("endpoint"),
            deployment=llm_dict.get("deployment", "gpt-5.4"),
            api_version=llm_dict.get("api_version", "2024-05-01-preview"),
            temperature=llm_dict.get("temperature", 1.0),
            max_tokens=llm_dict.get("max_tokens", 700),
            debug=llm_dict.get("debug", False),
            log_prompts=llm_dict.get("log_prompts", False),
            table_row_limit=llm_dict.get("table_row_limit", 200),
            summary_table_row_limit=llm_dict.get("summary_table_row_limit", 40),
            max_prompt_chars=llm_dict.get("max_prompt_chars", 120000),
            context_format=llm_dict.get("context_format", "csv")
        )

        return cls(
            project=project,
            fields_mapping=fields_mapping,
            auto_mapping=auto_mapping,
            auto_env_mapping=auto_env_mapping,
            env_value_mapping=env_value_mapping,
            auto_classification=auto_classification,
            enabled_metrics=enabled_metrics,
            metric_params=metric_params,
            exclude_statuses=exclude_statuses,
            llm=llm_config
        )

    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        Convert back to legacy YAML dict format for backward compatibility.

        This is useful for passing to legacy code that expects the old format.
        """
        llm_dict = {}
        if self.llm is not None:
            llm_dict = {
                "enabled": self.llm.enabled,
                "prompts_dir": self.llm.prompts_dir,
                "provider": self.llm.provider,
                "endpoint": self.llm.endpoint,
                "deployment": self.llm.deployment,
                "api_version": self.llm.api_version,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "debug": self.llm.debug,
                "log_prompts": self.llm.log_prompts,
                "table_row_limit": self.llm.table_row_limit,
                "summary_table_row_limit": self.llm.summary_table_row_limit,
                "max_prompt_chars": self.llm.max_prompt_chars,
                "context_format": self.llm.context_format
            }
        else:
            llm_dict = {"enabled": False}
        
        return {
            "project": {
                "timezone": self.project.timezone,
                **({"name": self.project.name} if self.project.name else {})
            },
            "fields_mapping": self.fields_mapping,
            "metrics": {
                "enabled": self.enabled_metrics,
                "params": self.metric_params
            },
            "exclude_statuses": self.exclude_statuses,
            "llm": llm_dict
        }


@dataclass
class AnalysisResult:
    """
    Pure data output from analysis - UI agnostic.

    Contains all metric results, LLM insights, and metadata.
    Different UIs (CLI HTML, Streamlit, API) can render this however they want.
    """
    # Metric results keyed by metric ID
    metrics_results: Dict[str, MetricResult]

    # Pre-computed summary KPIs (calculated from metrics_results)
    summary_kpis: Optional[SummaryKPIs] = None

    # LLM-generated insights per metric (if enabled)
    metric_insights: Dict[str, str] = field(default_factory=dict)

    # Overall LLM summary across all metrics (if enabled)
    overall_summary: str = ""

    # Data profile (if profiling enabled)
    data_profile: Optional[DataProfile] = None

    # Metadata about the analysis run
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def metric_ids(self) -> List[str]:
        """Get list of metric IDs in order."""
        return list(self.metrics_results.keys())
