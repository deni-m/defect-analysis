"""Integration tests for all metrics through AnalysisService.

These tests verify that metrics work correctly when called through the full analysis pipeline,
including normalization, filtering, and configuration handling.
"""
import pandas as pd
import pytest
from qa_bugs.services import AnalysisService, AnalysisConfig


@pytest.fixture
def base_data():
    """Standard test dataset with various bug states."""
    return pd.DataFrame([
        # Normal bugs
        {"Key": "B-1", "Created": "2024-01-01", "resolutiondate": "", "Status": "Open", "Priority": "High", "Environment": "QA"},
        {"Key": "B-2", "Created": "2024-01-02", "resolutiondate": "2024-01-10", "Status": "Closed", "Priority": "Medium", "Environment": "QA"},
        {"Key": "B-3", "Created": "2024-01-03", "resolutiondate": "2024-01-08", "Status": "Done", "Priority": "Low", "Environment": "DEV"},
        # Leaked bug
        {"Key": "B-4", "Created": "2024-01-04", "resolutiondate": "2024-01-12", "Status": "Closed", "Priority": "High", "Environment": "Prod"},
        # Rejected bugs
        {"Key": "B-5", "Created": "2024-01-05", "resolutiondate": "2024-01-06", "Status": "Rejected", "Priority": "Low", "Environment": "DEV"},
        {"Key": "B-6", "Created": "2024-01-06", "resolutiondate": "2024-01-07", "Status": "Cancelled", "Priority": "Low", "Environment": "QA"},
        {"Key": "B-7", "Created": "2024-01-07", "resolutiondate": "2024-01-08", "Status": "Won't Fix", "Priority": "Medium", "Environment": "QA"},
    ])


def test_defect_age_integration(base_data):
    """Test defect_age metric through AnalysisService."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
        },
        enabled_metrics=["defect_age"],
        metric_params={
            "defect_age": {
                "open_statuses": ["Open", "In Progress"],
            },
        },
        exclude_statuses=["Cancelled", "Won't Fix"],  # Exclude 2 bugs
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)
    
    # Verify filtering worked
    assert result.metadata["total_records"] == 7
    assert result.metadata["filtered_records"] == 5  # 2 excluded
    
    # Verify metric computed correctly on filtered data
    defect_age_result = result.metrics_results["defect_age"]
    stats = defect_age_result.tables["stats"].iloc[0]
    
    assert stats["count"] == 5, "Should only see 5 bugs after exclusions"
    assert stats["open_count"] == 1, "Should have 1 open bug"
    assert stats["closed_count"] == 4, "Should have 4 closed bugs"
    assert stats["avg_age"] >= 0, "Average age should be non-negative"


def test_age_by_priority_integration(base_data):
    """Test age_by_priority metric through AnalysisService."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
        },
        enabled_metrics=["age_by_priority"],
        exclude_statuses=["Cancelled"],
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)
    
    # Verify metric result
    age_by_priority_result = result.metrics_results["age_by_priority"]
    by_priority = age_by_priority_result.tables["age_by_priority"]
    
    assert not by_priority.empty, "Should have age breakdown by priority"
    assert "priority" in by_priority.columns
    assert "avg_age" in by_priority.columns
    assert "count" in by_priority.columns
    
    # Should see High, Medium, Low priorities (after excluding Cancelled)
    priorities = set(by_priority["priority"].values)
    assert "High" in priorities
    assert "Medium" in priorities or "Low" in priorities


def test_leakage_rate_integration(base_data):
    """Test leakage_rate metric through AnalysisService."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
            "environment": "Environment",
        },
        enabled_metrics=["leakage_rate"],
        metric_params={
            "leakage_rate": {
                "intended_env": ["QA"],
                "leak_envs": ["Prod"],
            },
        },
        exclude_statuses=["Cancelled", "Won't Fix"],
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)
    
    # Verify metric result
    leakage_result = result.metrics_results["leakage_rate"]
    overall = leakage_result.tables["leakage_overall"].iloc[0]
    
    assert "leaked" in overall.index
    assert "total" in overall.index
    assert overall["leaked"] == 1, "Should detect 1 leaked bug (B-4 in Prod)"
    # Total should be bugs in QA or Prod (excluding Cancelled and Won't Fix)
    # B-1 (QA), B-2 (QA), B-4 (Prod), B-5 (DEV-excluded from leakage calc) = 3
    assert overall["total"] >= 1, "Should have at least the leaked bug"


def test_rejection_rate_integration(base_data):
    """Test rejection_rate metric through AnalysisService with exclusions."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
        },
        enabled_metrics=["rejection_rate"],
        metric_params={
            "rejection_rate": {
                "rejected_statuses": ["Rejected", "Cancelled", "Won't Fix"],
            },
        },
        exclude_statuses=["Cancelled", "Won't Fix"],  # These should NOT be excluded from rejection_rate
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)
    
    # Verify other metrics would see filtered data
    assert result.metadata["filtered_records"] == 5  # 2 excluded
    
    # But rejection_rate should see ALL 7 bugs
    rejection_result = result.metrics_results["rejection_rate"]
    rejection_summary = rejection_result.tables["rejection_summary"].iloc[0]
    
    assert rejection_summary["total"] == 7, "rejection_rate should see all 7 bugs"
    assert rejection_summary["rejected"] == 3, "Should count 3 rejected bugs (Rejected, Cancelled, Won't Fix)"
    assert rejection_summary["rejection_percent"] == pytest.approx(42.86, rel=0.01), "Should be ~42.86% rejection rate"


def test_cumulative_open_closed_integration(base_data):
    """Test cumulative_open_closed metric through AnalysisService."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
        },
        enabled_metrics=["cumulative_open_closed"],
        exclude_statuses=["Cancelled"],
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)
    
    # Verify metric result
    cumulative_result = result.metrics_results["cumulative_open_closed"]
    assert "cumulative" in cumulative_result.tables
    
    cumulative_df = cumulative_result.tables["cumulative"]
    assert not cumulative_df.empty, "Should have cumulative data"
    assert "date" in cumulative_df.columns
    assert "opened" in cumulative_df.columns
    assert "closed" in cumulative_df.columns
    assert "opened_hc" in cumulative_df.columns
    assert "closed_hc" in cumulative_df.columns


def test_status_by_severity_integration(base_data):
    """Test status_by_severity metric through AnalysisService."""
    # Add severity column to data
    data_with_severity = base_data.copy()
    data_with_severity["Severity"] = ["Critical", "Major", "Minor", "Major", "Minor", "Minor", "Major"]
    
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
            "severity": "Severity",
        },
        enabled_metrics=["status_by_severity"],
        metric_params={
            "status_by_severity": {
                "open_statuses": ["Open", "In Progress"],
                "closed_statuses": ["Closed", "Done"],
            },
        },
        exclude_statuses=["Cancelled"],
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=data_with_severity, llm_enabled=False)
    
    # Verify metric result
    status_result = result.metrics_results["status_by_severity"]
    assert "status_by_severity_summary" in status_result.tables
    assert "status_by_severity_pivot" in status_result.tables
    
    by_severity = status_result.tables["status_by_severity_summary"]
    assert not by_severity.empty, "Should have status breakdown by severity"
    assert "priority" in by_severity.columns
    assert "status" in by_severity.columns
    assert "count" in by_severity.columns


def test_defects_by_env_priority_integration(base_data):
    """Test defects_by_env_priority metric through AnalysisService."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
            "environment": "Environment",
        },
        enabled_metrics=["defects_by_env_priority"],
        metric_params={
            "defects_by_env_priority": {
                "env_order": ["DEV", "QA", "STAGE", "Prod"],
            },
        },
        exclude_statuses=["Cancelled", "Won't Fix"],
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)
    
    # Verify metric result
    env_priority_result = result.metrics_results["defects_by_env_priority"]
    assert "env_priority" in env_priority_result.tables
    
    by_env = env_priority_result.tables["env_priority"]
    assert not by_env.empty, "Should have defects breakdown by environment and priority"
    assert "environment" in by_env.columns
    assert "priority" in by_env.columns
    assert "count" in by_env.columns


def test_defects_by_priority_integration(base_data):
    """Test defects_by_priority metric through AnalysisService."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
        },
        enabled_metrics=["defects_by_priority"],
        exclude_statuses=["Cancelled", "Won't Fix"],
        llm=None
    )

    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)

    priority_result = result.metrics_results["defects_by_priority"]
    tbl = priority_result.tables["priority_counts"]
    rows = {row["priority"]: row for row in tbl.to_dict("records")}

    assert rows["High"]["count"] == 2
    assert rows["Low"]["count"] == 2
    assert rows["Medium"]["count"] == 1
    assert rows["High"]["percent"] == 40.0


def test_multiple_metrics_integration(base_data):
    """Test running multiple metrics together through AnalysisService."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
            "environment": "Environment",
        },
        enabled_metrics=[
            "defect_age",
            "age_by_priority",
            "leakage_rate",
            "rejection_rate",
        ],
        metric_params={
            "leakage_rate": {
                "intended_env": ["QA"],
                "leak_envs": ["Prod"],
            },
            "rejection_rate": {
                "rejected_statuses": ["Rejected", "Cancelled", "Won't Fix"],
            },
        },
        exclude_statuses=["Cancelled", "Won't Fix"],
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=base_data, llm_enabled=False)
    
    # Verify all metrics computed
    assert len(result.metrics_results) == 4
    assert "defect_age" in result.metrics_results
    assert "age_by_priority" in result.metrics_results
    assert "leakage_rate" in result.metrics_results
    assert "rejection_rate" in result.metrics_results
    
    # Verify rejection_rate sees unfiltered data
    rejection_summary = result.metrics_results["rejection_rate"].tables["rejection_summary"].iloc[0]
    assert rejection_summary["total"] == 7, "rejection_rate should see all 7 bugs"
    
    # Verify other metrics see filtered data
    defect_age_stats = result.metrics_results["defect_age"].tables["stats"].iloc[0]
    assert defect_age_stats["count"] == 5, "defect_age should see 5 filtered bugs"
    
    # Verify KPIs calculated correctly
    assert result.summary_kpis is not None
    assert result.summary_kpis.total_defects == 7  # Raw input count (set by analysis_service)
    assert result.summary_kpis.rejection_pct is not None
    assert result.summary_kpis.rejected_count == 3


def test_metrics_with_date_filters(base_data):
    """Test that metrics respect since/until date filters."""
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
        },
        enabled_metrics=["defect_age", "rejection_rate"],
        metric_params={
            "rejection_rate": {
                "rejected_statuses": ["Rejected", "Cancelled"],
            },
        },
        exclude_statuses=[],
        llm=None
    )
    
    service = AnalysisService(config)
    
    # Filter to only first 3 days
    result = service.run_analysis(
        df=base_data,
        since="2024-01-01",
        until="2024-01-03",
        llm_enabled=False
    )
    
    # Should only see bugs B-1, B-2, B-3 (created Jan 1-3)
    assert result.metadata["filtered_records"] == 3
    
    defect_age_stats = result.metrics_results["defect_age"].tables["stats"].iloc[0]
    assert defect_age_stats["count"] == 3, "Should only see 3 bugs in date range"
    
    # rejection_rate should also respect date filters (but not status filters)
    rejection_summary = result.metrics_results["rejection_rate"].tables["rejection_summary"].iloc[0]
    assert rejection_summary["total"] == 3, "rejection_rate should see 3 bugs in date range"
    assert rejection_summary["rejected"] == 0, "No rejected bugs in first 3 days"


if __name__ == "__main__":
    """Run integration tests manually."""
    import sys
    
    print("=" * 70)
    print("Running Metrics Integration Tests")
    print("=" * 70)
    
    base_data = pd.DataFrame([
        {"Key": "B-1", "Created": "2024-01-01", "resolutiondate": "", "Status": "Open", "Priority": "High", "Environment": "QA"},
        {"Key": "B-2", "Created": "2024-01-02", "resolutiondate": "2024-01-10", "Status": "Closed", "Priority": "Medium", "Environment": "QA"},
        {"Key": "B-3", "Created": "2024-01-03", "resolutiondate": "2024-01-08", "Status": "Done", "Priority": "Low", "Environment": "DEV"},
        {"Key": "B-4", "Created": "2024-01-04", "resolutiondate": "2024-01-12", "Status": "Closed", "Priority": "High", "Environment": "Prod"},
        {"Key": "B-5", "Created": "2024-01-05", "resolutiondate": "2024-01-06", "Status": "Rejected", "Priority": "Low", "Environment": "DEV"},
        {"Key": "B-6", "Created": "2024-01-06", "resolutiondate": "2024-01-07", "Status": "Cancelled", "Priority": "Low", "Environment": "QA"},
        {"Key": "B-7", "Created": "2024-01-07", "resolutiondate": "2024-01-08", "Status": "Won't Fix", "Priority": "Medium", "Environment": "QA"},
    ])
    
    try:
        print("\n[1/9] Testing defect_age integration...")
        test_defect_age_integration(base_data)
        print("✓ PASSED")
        
        print("\n[2/9] Testing age_by_priority integration...")
        test_age_by_priority_integration(base_data)
        print("✓ PASSED")
        
        print("\n[3/9] Testing leakage_rate integration...")
        test_leakage_rate_integration(base_data)
        print("✓ PASSED")
        
        print("\n[4/9] Testing rejection_rate integration...")
        test_rejection_rate_integration(base_data)
        print("✓ PASSED")
        
        print("\n[5/9] Testing cumulative_open_closed integration...")
        test_cumulative_open_closed_integration(base_data)
        print("✓ PASSED")
        
        print("\n[6/9] Testing status_by_severity integration...")
        test_status_by_severity_integration(base_data)
        print("✓ PASSED")
        
        print("\n[7/9] Testing defects_by_env_priority integration...")
        test_defects_by_env_priority_integration(base_data)
        print("✓ PASSED")
        
        print("\n[8/9] Testing multiple metrics integration...")
        test_multiple_metrics_integration(base_data)
        print("✓ PASSED")
        
        print("\n[9/9] Testing metrics with date filters...")
        test_metrics_with_date_filters(base_data)
        print("✓ PASSED")
        
        print("\n" + "=" * 70)
        print("✓ All integration tests PASSED!")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
