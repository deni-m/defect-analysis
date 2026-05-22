"""Tests for resolution-first, status-fallback logic in rejection_rate metric.

When a 'resolution' column is present, it is used to determine rejection.
When absent, 'status' is used as the proxy.
"""
import pandas as pd
import pytest
from qa_bugs.metrics.rejection_rate import RejectionRate
from qa_bugs.services.data_profiler import DataProfile, ResolutionProfile


CFG_DEFAULTS = {}  # empty cfg → metric uses built-in defaults


# ---------------------------------------------------------------------------
# Resolution column present
# ---------------------------------------------------------------------------

def test_uses_resolution_column_when_present():
    """status=Done, resolution=Cancelled → counted as rejected."""
    df = pd.DataFrame([
        {"status": "Done", "resolution": "Cancelled"},
        {"status": "Done", "resolution": "Fixed"},
        {"status": "Done", "resolution": "Fixed"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 1
    assert summary["total"] == 3


def test_resolution_rejected_regardless_of_status():
    """status=Done (not a 'rejected' status), resolution=Won't Fix → still rejected."""
    df = pd.DataFrame([
        {"status": "Done", "resolution": "Won't Fix"},
        {"status": "Done", "resolution": "Done"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 1


def test_status_rejected_but_resolution_fixed_not_counted():
    """When resolution column exists, status is ignored.
    status=Rejected but resolution=Fixed → NOT rejected."""
    df = pd.DataFrame([
        {"status": "Rejected", "resolution": "Fixed"},
        {"status": "Done", "resolution": "Fixed"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 0, (
        "When resolution column exists it takes priority; 'Fixed' is not a rejected resolution"
    )


def test_mixed_resolution_values():
    """Multiple rejected resolution values detected correctly."""
    df = pd.DataFrame([
        {"status": "Done", "resolution": "Cancelled"},
        {"status": "Done", "resolution": "Won't Fix"},
        {"status": "Done", "resolution": "Duplicate"},
        {"status": "Done", "resolution": "Fixed"},
        {"status": "Done", "resolution": "Fixed"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 3
    assert summary["total"] == 5
    assert round(summary["rejection_percent"], 1) == 60.0


def test_resolution_case_insensitive():
    """resolution value matching is case-insensitive."""
    df = pd.DataFrame([
        {"status": "Done", "resolution": "cancelled"},
        {"status": "Done", "resolution": "WONTFIX"},
        {"status": "Done", "resolution": "fixed"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 2


# ---------------------------------------------------------------------------
# Resolution column absent → fallback to status
# ---------------------------------------------------------------------------

def test_falls_back_to_status_when_no_resolution_column():
    """When resolution column is missing, status is used."""
    df = pd.DataFrame([
        {"status": "Rejected"},
        {"status": "Cancelled"},
        {"status": "Done"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 2
    assert summary["total"] == 3


def test_fallback_to_status_case_insensitive():
    df = pd.DataFrame([
        {"status": "rejected"},
        {"status": "open"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 1


# ---------------------------------------------------------------------------
# Config-driven rejected_resolutions
# ---------------------------------------------------------------------------

def test_config_rejected_resolutions_used_when_resolution_present():
    """Custom rejected_resolutions list is applied to the resolution column."""
    cfg = {"metrics": {"params": {"rejection_rate": {
        "rejected_resolutions": ["InvalidBug", "OutOfScope"],
    }}}}
    df = pd.DataFrame([
        {"status": "Done", "resolution": "InvalidBug"},
        {"status": "Done", "resolution": "OutOfScope"},
        {"status": "Done", "resolution": "Fixed"},
    ])
    res = RejectionRate().compute(df, cfg)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 2


def test_profile_rejected_resolutions_used_when_config_absent():
    """Profile-derived resolution classification should drive rejected values."""
    profile = DataProfile(
        fingerprint="test",
        available_fields=["status", "resolution"],
        field_completeness={"status": 100.0, "resolution": 100.0},
        resolution_profile=ResolutionProfile(
            all_resolutions=["Fixed", "OutOfScope"],
            rejected_resolutions=["OutOfScope"],
            accepted_resolutions=["Fixed"],
            other_resolutions=[],
            confidence=0.7,
            method_used="fuzzy",
        ),
    )
    df = pd.DataFrame([
        {"status": "Done", "resolution": "OutOfScope"},
        {"status": "Done", "resolution": "Fixed"},
    ])

    res = RejectionRate().compute(df, CFG_DEFAULTS, profile=profile)
    summary = res.tables["rejection_summary"].iloc[0]

    assert summary["rejected"] == 1


def test_config_rejected_resolutions_override_profile():
    """Explicit metric config remains authoritative over profile classification."""
    cfg = {"metrics": {"params": {"rejection_rate": {
        "rejected_resolutions": ["BusinessRejected"],
    }}}}
    profile = DataProfile(
        fingerprint="test",
        available_fields=["status", "resolution"],
        field_completeness={"status": 100.0, "resolution": 100.0},
        resolution_profile=ResolutionProfile(
            all_resolutions=["BusinessRejected", "OutOfScope"],
            rejected_resolutions=["OutOfScope"],
            accepted_resolutions=[],
            other_resolutions=["BusinessRejected"],
            confidence=0.7,
            method_used="fuzzy",
        ),
    )
    df = pd.DataFrame([
        {"status": "Done", "resolution": "BusinessRejected"},
        {"status": "Done", "resolution": "OutOfScope"},
    ])

    res = RejectionRate().compute(df, cfg, profile=profile)
    summary = res.tables["rejection_summary"].iloc[0]

    assert summary["rejected"] == 1


def test_config_rejected_statuses_used_as_fallback():
    """Custom rejected_statuses list is applied when no resolution column."""
    cfg = {"metrics": {"params": {"rejection_rate": {
        "rejected_statuses": ["WontDo"],
    }}}}
    df = pd.DataFrame([
        {"status": "WontDo"},
        {"status": "Done"},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    # CFG_DEFAULTS has no rejected_statuses so defaults apply;
    # but with the custom cfg it should match "WontDo" only if defaults include it.
    # Here we verify the custom cfg is respected:
    res2 = RejectionRate().compute(df, cfg)
    summary = res2.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 1


# ---------------------------------------------------------------------------
# Edge / error cases
# ---------------------------------------------------------------------------

def test_quality_notes_set_when_both_columns_missing():
    """No status and no resolution → quality_notes set."""
    df = pd.DataFrame([{"priority": "High"}])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    assert res.quality_notes
    assert "no status column" in res.quality_notes[0]


def test_resolution_all_null_falls_back_gracefully():
    """resolution column exists but all values are null → treat as no match (not rejected)."""
    df = pd.DataFrame([
        {"status": "Done", "resolution": None},
        {"status": "Rejected", "resolution": None},
    ])
    res = RejectionRate().compute(df, CFG_DEFAULTS)
    summary = res.tables["rejection_summary"].iloc[0]
    # resolution column present and all null → 0 rejected (null doesn't match any pattern)
    assert summary["rejected"] == 0
