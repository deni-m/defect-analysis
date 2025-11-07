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
