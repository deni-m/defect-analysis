import pandas as pd
from qa_bugs.metrics.leakage_rate import LeakageRate


def test_leakage_rate_with_leak_envs():
    df = pd.DataFrame([
        {"status": "In Progress", "environment": "QA"},
        {"status": "In Progress", "environment": "QA,PROD"},
        {"status": "Closed", "environment": "PROD"},
    ])
    metric = LeakageRate()
    params = {"leak_envs": ["PROD"], "exclude_statuses": []}
    res = metric.compute(df, params)
    overall = res.tables["leakage_overall"].iloc[0]
    # Two records have PROD present
    assert overall["leaked"] == 2
    assert overall["total"] == 3


def test_leakage_rate_with_intended_env_only():
    df = pd.DataFrame([
        {"status": "In Progress", "environment": "QA"},
        {"status": "In Progress", "environment": "QA,UAT"},
        {"status": "In Progress", "environment": "QA"},
    ])
    metric = LeakageRate()
    params = {"intended_env": ["QA"], "exclude_statuses": []}
    res = metric.compute(df, params)
    overall = res.tables["leakage_overall"].iloc[0]
    # One has UAT outside intended
    assert overall["leaked"] == 1
    assert overall["total"] == 3


def test_leakage_rate_fallback():
    df = pd.DataFrame([
        {"status": "In Progress", "environment": ""},
        {"status": "In Progress", "environment": "UAT"},
    ])
    metric = LeakageRate()
    params = {"exclude_statuses": []}  # neither lists provided
    res = metric.compute(df, params)
    overall = res.tables["leakage_overall"].iloc[0]
    # Only one non-empty env -> leaked=1
    assert overall["leaked"] == 1
    assert overall["total"] == 2


def test_leakage_rate_rows_with_env_populated():
    """rows_with_env counts only rows that have at least one env token."""
    df = pd.DataFrame([
        {"status": "Open", "environment": "QA"},
        {"status": "Open", "environment": ""},
        {"status": "Open", "environment": None},
        {"status": "Open", "environment": "PROD"},
    ])
    metric = LeakageRate()
    res = metric.compute(df, {"exclude_statuses": []})
    overall = res.tables["leakage_overall"].iloc[0]
    assert overall["rows_with_env"] == 2


def test_leakage_rate_rows_with_env_all_empty():
    """rows_with_env is 0 when all environment values are empty."""
    df = pd.DataFrame([
        {"status": "Open", "environment": ""},
        {"status": "Open", "environment": None},
        {"status": "Open", "environment": ""},
    ])
    metric = LeakageRate()
    res = metric.compute(df, {"exclude_statuses": []})
    overall = res.tables["leakage_overall"].iloc[0]
    assert overall["rows_with_env"] == 0


def test_leakage_rate_by_priority_uses_prefixed_priority_order_without_profile():
    df = pd.DataFrame([
        {"status": "Closed", "environment": "QA", "priority": "2-Major"},
        {"status": "Closed", "environment": "PROD", "priority": "4-Minor"},
        {"status": "Closed", "environment": "QA", "priority": "1-Critical"},
        {"status": "Closed", "environment": "PROD", "priority": "0-Showstopper"},
        {"status": "Closed", "environment": "QA", "priority": "3-Average"},
    ])

    result = LeakageRate().compute(df, {"leak_envs": ["PROD"], "exclude_statuses": []})
    priorities = result.tables["leakage_by_priority"]["priority"].astype(str).tolist()
    html = LeakageRate().build_figure(result)

    assert priorities == ["0-Showstopper", "1-Critical", "2-Major", "3-Average", "4-Minor"]
    assert '"categoryarray":["0-Showstopper","1-Critical","2-Major","3-Average","4-Minor"]' in html


def test_leakage_rate_adds_quarter_chart_without_llm_analysis_table():
    df = pd.DataFrame([
        {"status": "Closed", "environment": "QA", "created_at": "2025-01-10T00:00:00Z"},
        {"status": "Closed", "environment": "PROD", "created_at": "2025-02-10T00:00:00Z"},
        {"status": "Closed", "environment": "PROD", "created_at": "2025-04-10T00:00:00Z"},
        {"status": "Closed", "environment": "QA", "created_at": "2025-04-11T00:00:00Z"},
        {"status": "Closed", "environment": "QA", "created_at": "not-a-date"},
    ])

    result = LeakageRate().compute(df, {"leak_envs": ["PROD"], "exclude_statuses": []})
    by_quarter = result.tables["leakage_by_quarter"]
    html = LeakageRate().build_figure(result)
    payload = result.payload()

    assert by_quarter["quarter"].tolist() == ["2025Q1", "2025Q2"]
    assert by_quarter["total"].tolist() == [2, 2]
    assert by_quarter["leaked"].tolist() == [1, 1]
    assert by_quarter["leakage_percent"].tolist() == [50.0, 50.0]
    assert "Defect Leakage by Quarter" in html
    assert "2025Q1" in html
    assert "2025Q2" in html
    assert "leakage_by_quarter" not in payload["tables"]
