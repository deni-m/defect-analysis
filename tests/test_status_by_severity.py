import pandas as pd
from qa_bugs.metrics.status_by_severity import StatusBySeverity


def test_status_by_severity_distribution():
    df = pd.DataFrame([
        {"priority": "High", "status": "Open"},
        {"priority": "High", "status": "Done"},
        {"priority": "Low", "status": "Open"},
        {"priority": "Low", "status": "Open"},
        {"priority": "Medium", "status": None},
    ])
    metric = StatusBySeverity()
    res = metric.compute(df, {})
    summary = res.tables["status_by_severity_summary"]
    assert not summary.empty
    # Check percent sums per priority to ~100
    pct_sums = summary.groupby("priority")["percent_priority"].sum().round(0)
    assert (pct_sums >= 99).all()


def test_status_by_severity_llm_payload():
    """Verify LLM payload contains only the simplified table."""
    df = pd.DataFrame([
        {"priority": "Critical", "status": "Done"},
        {"priority": "Critical", "status": "Done"},
        {"priority": "High", "status": "Cancelled"},
        {"priority": "High", "status": "Done"},
    ])
    metric = StatusBySeverity()
    res = metric.compute(df, {})

    # Verify all tables exist
    assert "status_by_severity_raw" in res.tables
    assert "status_by_severity_summary" in res.tables
    assert "status_by_severity_pivot" in res.tables
    assert "status_by_severity_llm" in res.tables

    # Verify LLM payload only contains the simplified table
    payload = res.payload()
    assert "tables" in payload
    assert list(payload["tables"].keys()) == ["status_by_severity_llm"]

    # Verify simplified table structure (severity, status, count)
    llm_table = payload["tables"]["status_by_severity_llm"]
    assert len(llm_table) > 0
    assert all("severity" in row for row in llm_table)
    assert all("status" in row for row in llm_table)
    assert all("count" in row for row in llm_table)
    # Should NOT contain percent columns
    assert all("percent_priority" not in row for row in llm_table)
    assert all("percent_overall" not in row for row in llm_table)


def test_status_by_severity_uses_prefixed_priority_order_without_profile():
    df = pd.DataFrame([
        {"priority": "2-Major", "status": "Done"},
        {"priority": "4-Minor", "status": "Done"},
        {"priority": "1-Critical", "status": "Done"},
        {"priority": "0-Showstopper", "status": "Done"},
        {"priority": "3-Average", "status": "Done"},
    ])

    result = StatusBySeverity().compute(df, {})
    html = StatusBySeverity().build_figure(result)

    assert '"categoryarray":["0-Showstopper","1-Critical","2-Major","3-Average","4-Minor"]' in html
