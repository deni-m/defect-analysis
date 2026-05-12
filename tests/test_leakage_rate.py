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
