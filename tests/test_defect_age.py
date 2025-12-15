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


def test_defect_age_open_closed_and_closed_age(sample_df):
        """DefectAge stats should expose consistent open/closed counts and closed age.

        sample_df from conftest has 3 rows:
            - 2 resolved, 1 open
            - created/resolved timestamps are spaced so closed ages are known.
        This test locks in the contract used by the AI Summary KPIs.
        """
        metric = DefectAge()
        res = metric.compute(sample_df, {})

        stats_df = res.tables["stats"]
        assert stats_df.shape[0] == 1
        stats = stats_df.iloc[0].to_dict()

        # All-time counts
        assert stats["count"] == 3
        assert stats["open_count"] == 1
        assert stats["closed_count"] == 2

        # Closed age is mean age (in days) of the two closed defects
        # Compute directly from the defect_age helper table for robustness
        defect_age_tbl = res.tables["defect_age"]
        closed_mask = defect_age_tbl["resolved_at"].notna()
        expected_closed_mean = float(defect_age_tbl.loc[closed_mask, "age_days"].mean())
        assert stats["avg_age_closed"] == expected_closed_mean
