import pandas as pd
from qa_bugs.metrics.age_by_priority import AgeByPriority


def test_age_by_priority_aggregation():
    df = pd.DataFrame([
        {"created_at": "2025-10-01T00:00:00Z", "resolved_at": "2025-10-04T00:00:00Z", "priority": "High"},  # age 3
        {"created_at": "2025-10-02T00:00:00Z", "resolved_at": "2025-10-05T00:00:00Z", "priority": "High"},  # age 3
        {"created_at": "2025-10-01T00:00:00Z", "resolved_at": None, "priority": "Low"},               # unresolved -> ignored in avg only if NaT? (will take now, so just assert non-negative)
    ])
    metric = AgeByPriority()
    res = metric.compute(df, {})
    tbl = res.tables["age_by_priority"]
    high_row = tbl[tbl["priority"] == "High"].iloc[0]
    # Mean of 3 and 3 = 3
    assert round(high_row["avg_age"],2) == 3.0
    assert "p50" in tbl.columns and "p90" in tbl.columns
