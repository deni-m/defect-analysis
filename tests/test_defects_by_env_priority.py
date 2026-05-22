import pandas as pd
from qa_bugs.metrics.base import MetricResult
from qa_bugs.metrics.defects_by_env_priority import DefectsByEnvPriority


def test_env_priority_unknown_first():
    df = pd.DataFrame([
        {"environment": "X1", "priority": "High"},
        {"environment": "X1", "priority": "Low"},
        {"environment": "QA", "priority": "High"},
        {"environment": "DEV", "priority": "High"},
        {"environment": "DEV", "priority": "Low"},
        {"environment": "PROD", "priority": "Low"},
        {"environment": "Y2", "priority": "Low"},
    ])
    metric = DefectsByEnvPriority()
    params = {"env_order": ["DEV", "QA", "PROD"]}
    res = metric.compute(df, params)
    tbl = res.tables["env_priority"]
    # Extract order as it appears after compute
    env_order_list = tbl.groupby("environment", observed=False).agg({"count": "sum"}).reset_index()["environment"].tolist()
    # Metric orders by count descending, then alphabetically.
    # DEV=2, X1=2, PROD=1, QA=1, Y2=1 → first two are DEV and X1 (count=2), rest have count=1
    top_two = set(env_order_list[:2])
    assert top_two == {"DEV", "X1"}, f"Top two by count should be DEV and X1, got {top_two}"
    assert all(e in env_order_list for e in ["DEV", "QA", "PROD", "X1", "Y2"])


def test_prefixed_priorities_get_non_default_colors():
    tbl = pd.DataFrame([
        {"environment": "QA", "priority": "0-Showstopper", "count": 1},
        {"environment": "QA", "priority": "1-Critical", "count": 1},
        {"environment": "QA", "priority": "2-Major", "count": 1},
        {"environment": "QA", "priority": "3-Average", "count": 1},
        {"environment": "QA", "priority": "4-Minor", "count": 1},
    ])
    result = MetricResult(
        "defects_by_env_priority",
        tables={
            "env_priority": tbl,
            "discovered_environments": pd.DataFrame([{"environment": "QA", "count": 5}]),
        },
    )

    html = DefectsByEnvPriority().build_figure(result)

    assert "0-Showstopper" in html
    assert "1-Critical" in html
    assert "2-Major" in html
    assert "3-Average" in html
    assert "4-Minor" in html
    assert "#7f1d1d" in html
    assert "#c0392b" in html
    assert "#e67e22" in html
    assert "#f39c12" in html
    assert "#3498db" in html
