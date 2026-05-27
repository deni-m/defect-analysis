import pandas as pd

from qa_bugs.metrics.defects_by_status_environment import DefectsByStatusEnvironment
from qa_bugs.services import AnalysisConfig, AnalysisService


def test_defects_by_status_environment_counts_and_orders_environments():
    df = pd.DataFrame([
        {"environment": "QA", "status": "Open"},
        {"environment": "QA", "status": "Closed"},
        {"environment": "PROD", "status": "Closed"},
        {"environment": "DEV", "status": "Open"},
        {"environment": "DEV", "status": "Open"},
    ])

    result = DefectsByStatusEnvironment().compute(df, {})
    tbl = result.tables["status_environment"]
    rows = {
        (row["environment"], row["status"]): row["count"]
        for row in tbl.astype({"environment": str, "status": str}).to_dict("records")
    }

    assert rows[("DEV", "Open")] == 2
    assert rows[("QA", "Open")] == 1
    assert rows[("QA", "Closed")] == 1
    assert rows[("PROD", "Closed")] == 1
    assert result.tables["environment_counts"]["environment"].tolist() == ["DEV", "QA", "PROD"]


def test_defects_by_status_environment_chart_uses_environment_and_status_order():
    df = pd.DataFrame([
        {"environment": "QA", "status": "Open"},
        {"environment": "PROD", "status": "Closed"},
        {"environment": "QA", "status": "Closed"},
    ])

    result = DefectsByStatusEnvironment().compute(df, {})
    html = DefectsByStatusEnvironment().build_figure(result)

    assert "Defects by Status and Environment" in html
    assert '"categoryarray":["QA","PROD"]' in html
    assert '"categoryarray":["Closed","Open"]' in html


def test_defects_by_status_environment_chart_assigns_distinct_status_colors():
    statuses = [
        "Assigned",
        "Reopen",
        "Open",
        "Blocked",
        "In Development",
        "In UAT",
        "Ready for Production",
        "Ready for UAT",
        "Ready for QA",
        "In QA",
        "Development Complete",
        "Enhancement",
        "Closed",
        "Rejected",
    ]

    color_map = DefectsByStatusEnvironment._status_color_map(statuses)

    assert set(color_map) == set(statuses)
    assert len(set(color_map.values())) > 8
    assert color_map["Closed"] == "#2ca02c"
    assert color_map["Rejected"] == "#7f8c8d"
    assert color_map["Blocked"] == "#f1c40f"
    assert color_map["In QA"] == "#17becf"


def test_defects_by_status_environment_skipped_when_environment_missing():
    df = pd.DataFrame([
        {"Key": "B-1", "Status": "Open"},
        {"Key": "B-2", "Status": "Closed"},
    ])
    config = AnalysisConfig(
        fields_mapping={"key": "Key", "status": "Status"},
        enabled_metrics=["defects_by_status_environment"],
        llm=None,
    )

    result = AnalysisService(config).run_analysis(df=df, llm_enabled=False)

    assert "defects_by_status_environment" not in result.metrics_results
    assert result.metadata["skipped_metrics"]["defects_by_status_environment"] == ["environment"]
