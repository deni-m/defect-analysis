"""Test data profiler service."""
from unittest.mock import MagicMock

import pandas as pd
import pytest
from qa_bugs.services.data_profiler import DataProfiler, PriorityProfile, StatusProfile


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


def test_non_prod_is_not_classified_as_production_environment():
    """NON_PROD contains PROD text but must remain non-production."""
    profiler = DataProfiler(llm_service=None)

    profile = profiler._classify_environments(
        pd.Series(["DEV", "ETE", "PROD", "NON_PROD"]),
        config=None,
    )

    assert profile.production_envs == ["PROD"]
    assert "NON_PROD" in profile.non_production_envs
    assert profile.pipeline_order.index("NON_PROD") < profile.pipeline_order.index("PROD")


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


def test_fuzzy_priority_classification_standard():
    """Standard JIRA priority names are ordered correctly by fuzzy matching."""
    profiler = DataProfiler(llm_service=None)
    priorities = pd.Series(["Low", "Highest", "Medium", "High", "Lowest"])
    profile = profiler._classify_priorities(priorities, config=None)

    assert isinstance(profile, PriorityProfile)
    assert profile.method_used == "fuzzy"
    assert profile.severity_order.index("Highest") < profile.severity_order.index("High")
    assert profile.severity_order.index("High") < profile.severity_order.index("Medium")
    assert profile.severity_order.index("Medium") < profile.severity_order.index("Low")
    assert profile.severity_order.index("Low") < profile.severity_order.index("Lowest")


def test_fuzzy_priority_classification_showstopper():
    """Showstopper is ranked above Highest in fuzzy matching."""
    profiler = DataProfiler(llm_service=None)
    priorities = pd.Series(["High", "showstopper", "Highest", "Low"])
    profile = profiler._classify_priorities(priorities, config=None)

    assert profile.severity_order.index("showstopper") < profile.severity_order.index("Highest")


def test_fuzzy_priority_unknown_gets_warning():
    """Unrecognized priority names trigger a warning and are appended at end."""
    profiler = DataProfiler(llm_service=None)
    priorities = pd.Series(["High", "FooBarPriority", "Low"])
    profile = profiler._classify_priorities(priorities, config=None)

    assert "FooBarPriority" in profile.severity_order
    assert profile.severity_order.index("FooBarPriority") > profile.severity_order.index("Low")
    assert any("Unrecognized" in w for w in profile.warnings)
    assert profile.confidence < 0.6


def test_llm_priority_classification():
    """LLM path is used when llm_enabled and returns correctly ordered priorities."""
    llm_yaml = "severity_order:\n  - showstopper\n  - High\n  - Medium\n  - Low\n"
    mock_llm = MagicMock()
    mock_llm.enabled = True
    mock_llm.deployment = "gpt-4"
    mock_llm._chat.return_value = (True, llm_yaml, None)

    profiler = DataProfiler(llm_service=mock_llm)
    priorities = pd.Series(["High", "Low", "Medium", "showstopper"])
    profile = profiler._classify_priorities(priorities, config=None)

    assert profile.method_used == "llm"
    assert profile.confidence == 0.9
    assert profile.severity_order == ["showstopper", "High", "Medium", "Low"]
    assert profile.warnings == []


def test_llm_priority_classification_fallback_on_error():
    """Falls back to fuzzy when LLM call fails."""
    mock_llm = MagicMock()
    mock_llm.enabled = True
    mock_llm.deployment = "gpt-4"
    mock_llm._chat.return_value = (False, "", "connection error")

    profiler = DataProfiler(llm_service=mock_llm)
    priorities = pd.Series(["High", "Low", "Medium"])
    profile = profiler._classify_priorities(priorities, config=None)

    assert profile.method_used == "fuzzy"
    assert any("LLM classification failed" in w for w in profile.warnings)


def test_llm_priority_missing_values_are_appended():
    """If LLM omits a priority, it is appended at the end rather than dropped."""
    llm_yaml = "severity_order:\n  - High\n  - Low\n"  # Medium missing
    mock_llm = MagicMock()
    mock_llm.enabled = True
    mock_llm.deployment = "gpt-4"
    mock_llm._chat.return_value = (True, llm_yaml, None)

    profiler = DataProfiler(llm_service=mock_llm)
    priorities = pd.Series(["High", "Low", "Medium"])
    profile = profiler._classify_priorities(priorities, config=None)

    assert "Medium" in profile.severity_order
    assert profile.severity_order.index("Medium") > profile.severity_order.index("Low")


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
