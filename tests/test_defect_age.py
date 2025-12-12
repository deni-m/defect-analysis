import pandas as pd
from qa_bugs.metrics.defect_age import DefectAge


def test_defect_age_basic(sample_df):
    metric = DefectAge()
    res = metric.compute(sample_df, {})
    # Aggregated tables exist; oldest_samples removed in optimization
    assert "stats" in res.tables
    assert "age_by_priority" in res.tables
    assert "oldest_samples" not in res.tables

    stats_df = res.tables["stats"]
    assert stats_df.shape[0] == 1
    stats = stats_df.iloc[0].to_dict()
    for col in ["count", "avg_age", "p50", "p90"]:
        assert col in stats_df.columns
    assert stats["count"] == sample_df.shape[0]
    assert stats["avg_age"] >= 0

    by_prio = res.tables["age_by_priority"]
    if not by_prio.empty:
        for col in ["priority", "count", "avg_age", "p50", "p90", "max_age"]:
            assert col in by_prio.columns

    # Payload optimization: verify lean payload includes expected extra fields
    payload = res.payload()
    assert payload["metric_id"] == "defect_age"
    assert "open_closed_ratio" in payload
    assert "age_distribution_summary" in payload
    # No tables in LLM payload; all context provided via extra fields
    assert len(payload["tables"]) == 0  # tables list is empty
