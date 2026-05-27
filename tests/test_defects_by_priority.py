import pandas as pd

from qa_bugs.metrics.defects_by_priority import DefectsByPriority


def test_defects_by_priority_counts_and_percentages_preserve_labels():
    df = pd.DataFrame([
        {"priority": "1-Critical"},
        {"priority": "1-Critical"},
        {"priority": "2-Major"},
        {"priority": "4-Minor"},
    ])

    result = DefectsByPriority().compute(df, {})
    tbl = result.tables["priority_counts"]

    rows = {row["priority"]: row for row in tbl.to_dict("records")}
    assert rows["1-Critical"]["count"] == 2
    assert rows["1-Critical"]["percent"] == 50.0
    assert rows["2-Major"]["count"] == 1
    assert rows["2-Major"]["percent"] == 25.0
    assert rows["4-Minor"]["count"] == 1
    assert rows["4-Minor"]["percent"] == 25.0


def test_defects_by_priority_chart_uses_data_driven_colors():
    df = pd.DataFrame([
        {"priority": "0-Showstopper"},
        {"priority": "1-Critical"},
        {"priority": "2-Major"},
        {"priority": "3-Average"},
        {"priority": "4-Minor"},
    ])

    result = DefectsByPriority().compute(df, {})
    html = DefectsByPriority().build_figure(result)

    assert "0-Showstopper" in html
    assert "1-Critical" in html
    assert "#7f1d1d" in html
    assert "#c0392b" in html
    assert "#e67e22" in html
    assert "#f39c12" in html
    assert "#3498db" in html


def test_defects_by_priority_chart_labels_include_count_and_percent():
    df = pd.DataFrame([
        {"priority": "Critical"},
        {"priority": "Critical"},
        {"priority": "Minor"},
    ])

    result = DefectsByPriority().compute(df, {})
    html = DefectsByPriority().build_figure(result)

    assert "2 (66.67%)" in html
    assert "1 (33.33%)" in html


def test_defects_by_priority_uses_prefixed_priority_order_without_profile():
    df = pd.DataFrame([
        {"priority": "2-Major"},
        {"priority": "2-Major"},
        {"priority": "4-Minor"},
        {"priority": "1-Critical"},
        {"priority": "0-Showstopper"},
        {"priority": "3-Average"},
    ])

    result = DefectsByPriority().compute(df, {})
    priorities = result.tables["priority_counts"]["priority"].astype(str).tolist()
    html = DefectsByPriority().build_figure(result)

    assert priorities == ["0-Showstopper", "1-Critical", "2-Major", "3-Average", "4-Minor"]
    assert '"categoryarray":["0-Showstopper","1-Critical","2-Major","3-Average","4-Minor"]' in html
