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
