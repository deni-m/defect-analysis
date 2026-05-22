"""Disk-based E2E calculation tests.

These tests mimic the important part of a file upload without exercising UI
rendering: CSV on disk -> pandas read_csv -> field auto-mapping -> analysis
service -> exact metric/KPI assertions.
"""
from pathlib import Path

import pandas as pd
import pytest

from qa_bugs.ingest.field_mapper import FieldMappingService
from qa_bugs.services import AnalysisConfig, AnalysisService
from qa_bugs.services.models import AutoClassificationConfig, LLMConfig


DATA_DIR = Path(__file__).parent / "data"


def _run_uploaded_csv(csv_name: str, *, auto_classification: bool = True):
    df = pd.read_csv(DATA_DIR / csv_name)
    mapping_result = FieldMappingService(llm_service=None).auto_detect_mapping(df)
    assert mapping_result.valid, mapping_result.errors

    config = AnalysisConfig(
        fields_mapping=mapping_result.mapping,
        auto_classification=AutoClassificationConfig(enabled=auto_classification),
        enabled_metrics=[
            "defect_age",
            "age_by_priority",
            "cumulative_open_closed",
            "leakage_rate",
            "defects_by_env_priority",
            "rejection_rate",
        ],
        metric_params={
            "leakage_rate": {
                "intended_env": ["QA"],
                "leak_envs": ["PROD"],
            },
        },
        exclude_statuses=[],
        llm=LLMConfig(enabled=False),
    )

    return AnalysisService(config).run_analysis(df=df, llm_enabled=False), mapping_result


@pytest.mark.e2e
def test_uploaded_csv_calculates_expected_metrics_from_detected_fields():
    result, mapping_result = _run_uploaded_csv("calculation_full.csv")

    assert mapping_result.mapping["resolved_at"] == "Resolution Date"
    assert mapping_result.mapping["resolution"] == "Resolution"
    assert mapping_result.mapping["environment"] == "Environment"

    assert result.metadata["total_records"] == 6
    assert result.metadata["filtered_records"] == 6
    assert set(result.metadata["metrics_computed"]) == {
        "defect_age",
        "age_by_priority",
        "cumulative_open_closed",
        "leakage_rate",
        "defects_by_env_priority",
        "rejection_rate",
    }

    kpis = result.summary_kpis
    assert kpis.total_defects == 6
    assert kpis.closed_defects == 6
    assert kpis.opened_defects == 0
    assert kpis.open_pct == 0.0
    assert kpis.avg_age_closed == pytest.approx(17 / 6)
    assert kpis.leaked_count == 1
    assert kpis.leakage_pct == 16.67
    assert kpis.rejected_count == 3
    assert kpis.rejection_pct == 50.0

    defect_age_stats = result.metrics_results["defect_age"].tables["stats"].iloc[0]
    assert defect_age_stats["count"] == 6
    assert defect_age_stats["closed_count"] == 6
    assert defect_age_stats["open_count"] == 0
    assert defect_age_stats["avg_age_closed"] == pytest.approx(17 / 6)

    leakage = result.metrics_results["leakage_rate"].tables["leakage_overall"].iloc[0]
    assert leakage["total"] == 6
    assert leakage["leaked"] == 1
    assert leakage["caught"] == 5
    assert leakage["leakage_percent"] == 16.67

    rejection = result.metrics_results["rejection_rate"].tables["rejection_summary"].iloc[0]
    assert rejection["total"] == 6
    assert rejection["rejected"] == 3
    assert rejection["rejection_percent"] == 50.0

    env_priority = result.metrics_results["defects_by_env_priority"].tables["env_priority"]
    env_counts = env_priority.groupby("environment", observed=False)["count"].sum().to_dict()
    assert env_counts == {"QA": 3, "PROD": 1, "DEV": 1, "UAT": 1}


@pytest.mark.e2e
def test_uploaded_csv_uses_status_fallback_when_resolution_outcome_missing():
    result, mapping_result = _run_uploaded_csv(
        "calculation_status_fallback.csv",
        auto_classification=False,
    )

    assert mapping_result.mapping["resolved_at"] == "Resolution Date"
    assert "resolution" not in mapping_result.mapping

    rejection = result.metrics_results["rejection_rate"].tables["rejection_summary"].iloc[0]
    assert rejection["total"] == 4
    assert rejection["rejected"] == 3
    assert rejection["rejection_percent"] == 75.0

    kpis = result.summary_kpis
    assert kpis.total_defects == 4
    assert kpis.rejected_count == 3
    assert kpis.rejection_pct == 75.0
