"""Test data profiler service."""
import pandas as pd
import pytest
from qa_bugs.services.data_profiler import DataProfiler, StatusProfile


def test_fuzzy_status_classification():
    """Test fuzzy keyword matching for status classification."""
    profiler = DataProfiler(llm_service=None)
    
    # Create test data with various status names
    statuses = pd.Series([
        "Open", "In Progress", "Done", "Resolved",
        "Cancelled", "Rejected", "To Do", "Closed"
    ])
    
    profile = profiler._classify_statuses(statuses, config=None)
    
    # Verify classification
    assert isinstance(profile, StatusProfile)
    assert "Open" in profile.open_statuses or "Open" in profile.open_statuses
    assert "In Progress" in profile.open_statuses
    assert "Done" in profile.closed_statuses
    assert "Resolved" in profile.closed_statuses
    assert "Closed" in profile.closed_statuses
    assert "Cancelled" in profile.rejected_statuses
    assert "Rejected" in profile.rejected_statuses
    
    # Method should be fuzzy
    assert profile.method_used == "fuzzy"
    assert 0 < profile.confidence <= 1.0


def test_data_profiler_basic():
    """Test basic data profiling workflow."""
    profiler = DataProfiler(llm_service=None, cache_enabled=False)
    
    # Create sample data
    df = pd.DataFrame({
        "key": ["BUG-1", "BUG-2", "BUG-3"],
        "status": ["Open", "Done", "Rejected"],
        "priority": ["High", "Medium", "Low"],
        "environment": ["QA", "PROD", "DEV"],
        "created_at": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    })
    
    # Profile data
    profile = profiler.profile_data(
        df,
        classify_statuses=True,
        classify_priorities=True,
        classify_environments=True
    )
    
    # Verify profile structure
    assert profile.available_fields == df.columns.tolist()
    assert profile.date_range is not None
    assert profile.status_profile is not None
    assert profile.priority_profile is not None
    assert profile.environment_profile is not None
    
    # Verify status classification
    assert "Open" in profile.status_profile.open_statuses
    assert "Done" in profile.status_profile.closed_statuses
    assert "Rejected" in profile.status_profile.rejected_statuses
    
    # Verify environment classification
    assert "QA" in profile.environment_profile.all_environments
    assert "PROD" in profile.environment_profile.all_environments


def test_profile_caching():
    """Test that profiler caches results by data fingerprint."""
    profiler = DataProfiler(llm_service=None, cache_enabled=True)
    
    df = pd.DataFrame({
        "status": ["Open", "Done"],
        "priority": ["High", "Low"]
    })
    
    # First call - should profile
    profile1 = profiler.profile_data(df, classify_statuses=True)
    fingerprint1 = profile1.fingerprint
    
    # Second call with same data - should use cache
    profile2 = profiler.profile_data(df, classify_statuses=True)
    
    assert profile1.fingerprint == profile2.fingerprint
    assert fingerprint1 in profiler._cache
    
    # Different data - should create new profile
    df2 = pd.DataFrame({
        "status": ["Open", "Done", "Cancelled"],
        "priority": ["High", "Low", "Medium"]
    })
    profile3 = profiler.profile_data(df2, classify_statuses=True)
    
    assert profile3.fingerprint != profile1.fingerprint


def test_format_profile_summary():
    """Test profile summary formatting."""
    profiler = DataProfiler(llm_service=None)
    
    df = pd.DataFrame({
        "status": ["Open", "Done", "Rejected"],
        "priority": ["High", "Low", "Medium"],
        "created_at": pd.to_datetime(["2024-01-01", "2024-01-15", "2024-01-30"])
    })
    
    profile = profiler.profile_data(df, classify_statuses=True, classify_priorities=True)
    
    # Format summary
    summary = profiler.format_profile_summary(profile)
    
    # Verify summary contains key information
    assert "Data Profile" in summary
    assert "confidence" in summary.lower()
    assert "Status Classification" in summary
    assert "Open:" in summary
    assert "Closed:" in summary
    assert "Rejected:" in summary
