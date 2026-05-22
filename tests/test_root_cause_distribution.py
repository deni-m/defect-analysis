import pandas as pd

from qa_bugs.metrics.root_cause_distribution import RootCauseDistribution


def test_root_cause_distribution_top_groups_and_other_rollup():
    rows = (
        [{"root_cause": "Requirements gap"}] * 5
        + [{"root_cause": "Code defect"}] * 3
        + [{"root_cause": "Environment issue"}] * 2
        + [{"root_cause": f"Rare cause {i}"} for i in range(1, 12)]
        + [{"root_cause": ""}, {"root_cause": None}]
    )
    df = pd.DataFrame(rows)

    result = RootCauseDistribution().compute(df, {"top_n": 3})
    counts = result.tables["root_cause_counts"]
    coverage = result.tables["root_cause_coverage"].iloc[0]
    by_cause = {row["root_cause"]: row for row in counts.to_dict("records")}

    assert by_cause["Requirements gap"]["count"] == 5
    assert by_cause["Code defect"]["count"] == 3
    assert by_cause["Environment issue"]["count"] == 2
    assert by_cause["Other"]["count"] == 11
    assert by_cause["Requirements gap"]["percent"] == 23.81
    assert by_cause["Requirements gap"]["percent_of_specified"] == 23.81
    assert by_cause["Requirements gap"]["percent_of_total"] == 21.74
    assert coverage["total_defects"] == 23
    assert coverage["specified_defects"] == 21
    assert coverage["unspecified_defects"] == 2
    assert coverage["unique_root_causes"] == 14


def test_root_cause_distribution_skips_when_column_missing_or_empty():
    missing = RootCauseDistribution().compute(pd.DataFrame([{"priority": "High"}]), {})
    empty = RootCauseDistribution().compute(pd.DataFrame([{"root_cause": ""}, {"root_cause": pd.NA}]), {})

    assert missing.skip_report is True
    assert empty.skip_report is True


def test_root_cause_distribution_chart_labels_include_count_and_percent():
    df = pd.DataFrame([
        {"root_cause": "Requirements gap"},
        {"root_cause": "Requirements gap"},
        {"root_cause": "Code defect"},
    ])

    result = RootCauseDistribution().compute(df, {})
    html = RootCauseDistribution().build_figure(result)

    assert "Requirements gap" in html
    assert "#3498db" in html
    assert "Top Root Cause Groups (% of specified root causes)" in html
    assert "2 (66.67%)" in html
    assert "1 (33.33%)" in html


def test_root_cause_distribution_skips_free_text_like_values():
    df = pd.DataFrame([
        {
            "root_cause": (
                "This defect has a long narrative root cause description with ticket links, "
                f"implementation details, and one-off context number {idx}."
            )
        }
        for idx in range(20)
    ])

    result = RootCauseDistribution().compute(df, {})

    assert result.skip_report is True
    assert "free-text descriptions" in result.summary


def test_root_cause_distribution_truncates_long_repeated_labels_in_chart():
    long_label = (
        "Configuration issue caused by a repeated long component name that should not "
        "take over the whole chart"
    )
    df = pd.DataFrame([{"root_cause": long_label}] * 3)

    result = RootCauseDistribution().compute(df, {})
    html = RootCauseDistribution().build_figure(result)

    assert RootCauseDistribution._truncate_label(long_label) in html
    assert "3 (100.00%)" in html
