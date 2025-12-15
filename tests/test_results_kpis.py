"""Tests for KPI calculator service."""
import pandas as pd
import pytest
from qa_bugs.metrics.base import MetricResult
from qa_bugs.services.models import AnalysisResult
from qa_bugs.services.kpi_calculator import (
    calculate_summary_kpis,
    SummaryKPIs,
    _extract_defect_age_kpis,
    _extract_cumulative_kpis,
    _extract_leakage_kpis,
    _extract_rejection_kpis,
)


def _make_metric_result(metric_id: str, tables: dict) -> MetricResult:
    """Helper to create MetricResult for testing."""
    return MetricResult(metric_id, tables=tables, summary="")


# --- Tests for main calculate_summary_kpis function ---


def test_calculate_summary_kpis_from_defect_age_stats():
    """Test KPI calculation from complete defect_age stats."""
    stats_df = pd.DataFrame([
        {
            "count": 10,
            "avg_age": 5.5,
            "p50": 5.0,
            "p90": 9.0,
            "avg_age_closed": 4.0,
            "open_count": 3,
            "closed_count": 7,
        }
    ])
    defect_res = _make_metric_result("defect_age", {"stats": stats_df})
    analysis = AnalysisResult(metrics_results={"defect_age": defect_res})

    kpis = calculate_summary_kpis(analysis)

    assert kpis.total_defects == 10
    assert kpis.avg_age_all == 5.5
    assert kpis.avg_age_closed == 4.0
    assert kpis.opened_defects == 3
    assert kpis.closed_defects == 7
    assert kpis.open_pct == 30.0  # (3/10) * 100


def test_calculate_summary_kpis_defect_age_fallback():
    """Test fallback to defect_age table when stats are incomplete."""
    stats_df = pd.DataFrame([
        {
            "count": 2,
            "avg_age": 3.0,
            "p50": 3.0,
            "p90": 3.0,
        }
    ])
    defect_age_tbl = pd.DataFrame(
        [
            {"resolved_at": pd.Timestamp("2025-01-02"), "age_days": 2.0},
            {"resolved_at": pd.NaT, "age_days": 5.0},
        ]
    )
    defect_res = _make_metric_result(
        "defect_age",
        {"stats": stats_df, "defect_age": defect_age_tbl},
    )
    analysis = AnalysisResult(metrics_results={"defect_age": defect_res})

    kpis = calculate_summary_kpis(analysis)

    assert kpis.total_defects == 2
    assert kpis.closed_defects == 1
    assert kpis.opened_defects == 1
    assert kpis.avg_age_closed == 2.0
    assert kpis.open_pct == 50.0


def test_calculate_summary_kpis_from_leakage_and_rejection():
    """Test KPI calculation from leakage and rejection metrics."""
    leakage_overall = pd.DataFrame([
        {
            "rate_percent": 12.5,
            "leaked": 3,
            "total": 24,
        }
    ])
    rejection_summary = pd.DataFrame([
        {
            "rejected": 4,
            "total": 20,
            "rejection_percent": 20.0,
        }
    ])

    leakage_res = _make_metric_result("leakage_rate", {"leakage_overall": leakage_overall})
    rejection_res = _make_metric_result("rejection_rate", {"rejection_summary": rejection_summary})

    analysis = AnalysisResult(
        metrics_results={
            "leakage_rate": leakage_res,
            "rejection_rate": rejection_res,
        }
    )

    kpis = calculate_summary_kpis(analysis)

    assert kpis.leakage_pct == 12.5
    assert kpis.leaked_count == 3
    assert kpis.rejection_pct == 20.0
    assert kpis.rejected_count == 4


def test_calculate_summary_kpis_combined():
    """Test KPI calculation from multiple metrics together."""
    stats_df = pd.DataFrame([
        {
            "count": 50,
            "avg_age": 12.5,
            "p50": 10.0,
            "p90": 20.0,
            "avg_age_closed": 8.5,
            "open_count": 15,
            "closed_count": 35,
        }
    ])
    leakage_overall = pd.DataFrame([
        {"rate_percent": 8.0, "leaked": 4, "total": 50}
    ])
    rejection_summary = pd.DataFrame([
        {"rejected": 5, "total": 50, "rejection_percent": 10.0}
    ])

    analysis = AnalysisResult(
        metrics_results={
            "defect_age": _make_metric_result("defect_age", {"stats": stats_df}),
            "leakage_rate": _make_metric_result("leakage_rate", {"leakage_overall": leakage_overall}),
            "rejection_rate": _make_metric_result("rejection_rate", {"rejection_summary": rejection_summary}),
        }
    )

    kpis = calculate_summary_kpis(analysis)

    assert kpis.total_defects == 50
    assert kpis.opened_defects == 15
    assert kpis.closed_defects == 35
    assert kpis.open_pct == 30.0
    assert kpis.avg_age_all == 12.5
    assert kpis.avg_age_closed == 8.5
    assert kpis.leakage_pct == 8.0
    assert kpis.leaked_count == 4
    assert kpis.rejection_pct == 10.0
    assert kpis.rejected_count == 5


def test_calculate_summary_kpis_empty_result():
    """Test KPI calculation with no metrics."""
    analysis = AnalysisResult(metrics_results={})
    kpis = calculate_summary_kpis(analysis)

    assert kpis.total_defects is None
    assert kpis.opened_defects is None
    assert kpis.closed_defects is None
    assert kpis.open_pct is None
    assert kpis.avg_age_all is None
    assert kpis.avg_age_closed is None
    assert kpis.leakage_pct is None
    assert kpis.leaked_count is None
    assert kpis.rejection_pct is None
    assert kpis.rejected_count is None


# --- Tests for individual extraction functions ---


def test_extract_defect_age_kpis_from_stats():
    """Test extraction from defect_age stats table."""
    stats_df = pd.DataFrame([
        {
            "count": 20,
            "avg_age": 7.5,
            "p50": 6.0,
            "p90": 15.0,
            "avg_age_closed": 5.5,
            "open_count": 8,
            "closed_count": 12,
        }
    ])
    metric_result = _make_metric_result("defect_age", {"stats": stats_df})
    kpis = SummaryKPIs()

    _extract_defect_age_kpis(metric_result, kpis)

    assert kpis.total_defects == 20
    assert kpis.avg_age_all == 7.5
    assert kpis.avg_age_closed == 5.5
    assert kpis.opened_defects == 8
    assert kpis.closed_defects == 12


def test_extract_defect_age_kpis_fallback_to_table():
    """Test fallback to defect_age detail table."""
    stats_df = pd.DataFrame([{"count": 3, "avg_age": 4.0, "p50": 4.0, "p90": 5.0}])
    defect_age_tbl = pd.DataFrame([
        {"resolved_at": pd.Timestamp("2025-01-01"), "age_days": 3.0},
        {"resolved_at": pd.Timestamp("2025-01-02"), "age_days": 4.0},
        {"resolved_at": pd.NaT, "age_days": 6.0},
    ])
    metric_result = _make_metric_result("defect_age", {"stats": stats_df, "defect_age": defect_age_tbl})
    kpis = SummaryKPIs()

    _extract_defect_age_kpis(metric_result, kpis)

    assert kpis.total_defects == 3
    assert kpis.closed_defects == 2
    assert kpis.opened_defects == 1
    assert kpis.avg_age_closed == 3.5  # (3+4)/2


def test_extract_cumulative_kpis():
    """Test extraction from cumulative_open_closed metric."""
    summary_df = pd.DataFrame([{"opened_cum": 25, "closed_cum": 18}])
    metric_result = _make_metric_result("cumulative_open_closed", {"summary": summary_df})
    kpis = SummaryKPIs()

    _extract_cumulative_kpis(metric_result, kpis)

    assert kpis.opened_defects == 25
    assert kpis.closed_defects == 18
    assert kpis.total_defects == 25


def test_extract_cumulative_kpis_does_not_override():
    """Test that cumulative metric doesn't override existing defect_age stats."""
    summary_df = pd.DataFrame([{"opened_cum": 100, "closed_cum": 80}])
    metric_result = _make_metric_result("cumulative_open_closed", {"summary": summary_df})
    kpis = SummaryKPIs()
    # Pre-populate from defect_age
    kpis.opened_defects = 50
    kpis.closed_defects = 40

    _extract_cumulative_kpis(metric_result, kpis)

    # Should NOT override
    assert kpis.opened_defects == 50
    assert kpis.closed_defects == 40


def test_extract_leakage_kpis():
    """Test extraction from leakage_rate metric."""
    leakage_df = pd.DataFrame([
        {"rate_percent": 15.5, "leaked": 7, "total": 45}
    ])
    metric_result = _make_metric_result("leakage_rate", {"leakage_overall": leakage_df})
    kpis = SummaryKPIs()

    _extract_leakage_kpis(metric_result, kpis)

    assert kpis.leakage_pct == 15.5
    assert kpis.leaked_count == 7
    assert kpis.total_defects == 45


def test_extract_leakage_kpis_legacy_table():
    """Test extraction from legacy leakage_overall_kpis table."""
    legacy_df = pd.DataFrame([
        {"leakage_percent": 10.0, "leaked_count": 5, "total_considered": 50}
    ])
    metric_result = _make_metric_result("leakage_rate", {"leakage_overall_kpis": legacy_df})
    kpis = SummaryKPIs()

    _extract_leakage_kpis(metric_result, kpis)

    assert kpis.leakage_pct == 10.0
    assert kpis.leaked_count == 5
    assert kpis.total_defects == 50


def test_extract_rejection_kpis():
    """Test extraction from rejection_rate metric."""
    rejection_df = pd.DataFrame([
        {"rejected": 6, "total": 30, "rejection_percent": 20.0}
    ])
    metric_result = _make_metric_result("rejection_rate", {"rejection_summary": rejection_df})
    kpis = SummaryKPIs()

    _extract_rejection_kpis(metric_result, kpis)

    assert kpis.rejection_pct == 20.0
    assert kpis.rejected_count == 6
    assert kpis.total_defects == 30


def test_extract_rejection_kpis_alt_table():
    """Test extraction from alternative 'summary' table."""
    summary_df = pd.DataFrame([
        {"rejected": 8, "total": 40, "rejection_percent": 20.0}
    ])
    metric_result = _make_metric_result("rejection_rate", {"summary": summary_df})
    kpis = SummaryKPIs()

    _extract_rejection_kpis(metric_result, kpis)

    assert kpis.rejection_pct == 20.0
    assert kpis.rejected_count == 8
    assert kpis.total_defects == 40


def test_open_pct_calculation():
    """Test that open_pct is correctly derived."""
    stats_df = pd.DataFrame([
        {
            "count": 100,
            "avg_age": 10.0,
            "p50": 8.0,
            "p90": 20.0,
            "avg_age_closed": 7.0,
            "open_count": 30,
            "closed_count": 70,
        }
    ])
    analysis = AnalysisResult(
        metrics_results={"defect_age": _make_metric_result("defect_age", {"stats": stats_df})}
    )

    kpis = calculate_summary_kpis(analysis)

    assert kpis.open_pct == 30.0  # (100-70)/100 * 100


def test_zero_total_defects_no_pct():
    """Test that open_pct is None when total is 0."""
    stats_df = pd.DataFrame([
        {
            "count": 0,
            "avg_age": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "avg_age_closed": 0.0,
            "open_count": 0,
            "closed_count": 0,
        }
    ])
    analysis = AnalysisResult(
        metrics_results={"defect_age": _make_metric_result("defect_age", {"stats": stats_df})}
    )

    kpis = calculate_summary_kpis(analysis)

    assert kpis.total_defects == 0
    assert kpis.open_pct is None
