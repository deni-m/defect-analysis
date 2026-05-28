import pandas as pd
from qa_bugs.metrics.cumulative_open_closed import CumulativeOpenClosed


def test_cumulative_open_closed_trend():
    df = pd.DataFrame([
        {"created_at": "2025-10-01T10:00:00Z", "resolved_at": "2025-10-02T12:00:00Z", "priority": "Medium"},
        {"created_at": "2025-10-02T09:00:00Z", "resolved_at": None, "priority": "Low"},
        {"created_at": "2025-10-03T09:00:00Z", "resolved_at": "2025-10-05T00:00:00Z", "priority": "High"},
    ])
    metric = CumulativeOpenClosed()
    res = metric.compute(df, {})
    trend = res.tables["cumulative"]
    # Ensure monotonic non-decreasing
    assert (trend["opened"].diff().fillna(0) >= 0).all()
    assert (trend["closed"].diff().fillna(0) >= 0).all()
    # Final opened count equals total defects
    assert trend["opened"].iloc[-1] == 3


def test_cumulative_open_closed_prod_trend_and_filter_chart():
    df = pd.DataFrame([
        {"created_at": "2025-10-01T10:00:00Z", "resolved_at": "2025-10-02T12:00:00Z", "priority": "Medium", "environment": "QA"},
        {"created_at": "2025-10-02T09:00:00Z", "resolved_at": None, "priority": "High", "environment": "PROD"},
        {"created_at": "2025-10-03T09:00:00Z", "resolved_at": "2025-10-05T00:00:00Z", "priority": "Critical", "environment": "PROD"},
        {"created_at": "2025-10-04T09:00:00Z", "resolved_at": "2025-10-06T00:00:00Z", "priority": "Low", "environment": "QA,PROD"},
    ])

    result = CumulativeOpenClosed().compute(df, {})
    prod_trend = result.tables["prod_cumulative"]
    summary = result.tables["summary"].iloc[0]
    html = CumulativeOpenClosed().build_figure(result)

    assert prod_trend["opened"].iloc[-1] == 3
    assert prod_trend["closed"].iloc[-1] == 2
    assert prod_trend["opened_hc"].iloc[-1] == 2
    assert prod_trend["closed_hc"].iloc[-1] == 1
    assert summary["prod_opened_cum"] == 3
    assert summary["prod_closed_cum"] == 2
    assert "PROD Defects" in html
    assert "Opened High+Critical" in html
    assert "Closed High+Critical" in html
    assert "tozeroy" in html
    assert "rgba(239,85,59,0.35)" in html
    assert "dash" in html
