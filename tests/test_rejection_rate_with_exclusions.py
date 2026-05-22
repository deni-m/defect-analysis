"""Test that rejection_rate correctly counts rejected bugs even when some are excluded from other metrics."""
import pandas as pd
from qa_bugs.services import AnalysisService, AnalysisConfig


def test_rejection_rate_counts_excluded_statuses():
    """Verify that cancelled bugs are counted in rejection rate even if excluded from other metrics."""
    # Create test data with:
    # - 2 normal bugs (Open, Closed)
    # - 2 rejected bugs (Rejected, Cancelled)
    data = pd.DataFrame([
        {"Key": "B-1", "Created": "2024-01-01", "resolutiondate": "", "Status": "Open", "Priority": "High"},
        {"Key": "B-2", "Created": "2024-01-02", "resolutiondate": "2024-01-05", "Status": "Closed", "Priority": "Medium"},
        {"Key": "B-3", "Created": "2024-01-03", "resolutiondate": "2024-01-04", "Status": "Rejected", "Priority": "Low"},
        {"Key": "B-4", "Created": "2024-01-04", "resolutiondate": "2024-01-05", "Status": "Cancelled", "Priority": "Low"},
    ])
    
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
        exclude_statuses=["Cancelled"],  # Exclude Cancelled from lifecycle metrics
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=data, llm_enabled=False)
    
    # Verify metadata shows correct filtering
    assert result.metadata["total_records"] == 4, "Should have 4 total records"
    assert result.metadata["filtered_records"] == 3, "Should have 3 filtered records (1 Cancelled excluded)"
    
    # Verify defect_age only sees 3 bugs (Cancelled excluded)
    defect_age_result = result.metrics_results["defect_age"]
    stats = defect_age_result.tables["stats"].iloc[0]
    assert stats["count"] == 3, f"defect_age should only see 3 bugs, got {stats['count']}"
    
    # Verify rejection_rate sees ALL 4 bugs (including Cancelled)
    rejection_result = result.metrics_results["rejection_rate"]
    rejection_summary = rejection_result.tables["rejection_summary"].iloc[0]
    
    assert rejection_summary["total"] == 4, f"rejection_rate should see all 4 bugs, got {rejection_summary['total']}"
    assert rejection_summary["rejected"] == 2, f"Should count 2 rejected bugs (Rejected + Cancelled), got {rejection_summary['rejected']}"
    assert rejection_summary["rejection_percent"] == 50.0, f"Should be 50% rejection rate, got {rejection_summary['rejection_percent']}"
    
    # Verify KPIs
    # total_defects is set to the raw input row count by analysis_service (before exclusions)
    assert result.summary_kpis.total_defects == 4, "KPIs total_defects reflects raw input count (4 bugs before exclusions)"
    assert result.summary_kpis.rejection_pct == 50.0, "KPI rejection rate should be 50%"
    assert result.summary_kpis.rejected_count == 2, "KPI should show 2 rejected bugs"
    
    print("✓ Test passed: rejection_rate correctly counts excluded statuses")


def test_rejection_rate_without_exclusions():
    """Verify rejection_rate works correctly when no statuses are excluded."""
    data = pd.DataFrame([
        {"Key": "B-1", "Created": "2024-01-01", "resolutiondate": "", "Status": "Open", "Priority": "High"},
        {"Key": "B-2", "Created": "2024-01-02", "resolutiondate": "2024-01-05", "Status": "Closed", "Priority": "Medium"},
        {"Key": "B-3", "Created": "2024-01-03", "resolutiondate": "2024-01-04", "Status": "Won't Fix", "Priority": "Low"},
    ])
    
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
                "rejected_statuses": ["Won't Fix", "WONTFIX"],
            },
        },
        exclude_statuses=[],  # No exclusions
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=data, llm_enabled=False)
    
    rejection_result = result.metrics_results["rejection_rate"]
    rejection_summary = rejection_result.tables["rejection_summary"].iloc[0]
    
    assert rejection_summary["total"] == 3, "Should see all 3 bugs"
    assert rejection_summary["rejected"] == 1, "Should count 1 rejected bug"
    assert rejection_summary["rejection_percent"] == 33.33, "Should be 33.33% rejection rate"
    
    print("✓ Test passed: rejection_rate works without exclusions")


def test_rejection_rate_multiple_excluded_statuses():
    """Test with multiple excluded statuses that are also rejection statuses."""
    data = pd.DataFrame([
        {"Key": "B-1", "Created": "2024-01-01", "resolutiondate": "", "Status": "Open", "Priority": "High"},
        {"Key": "B-2", "Created": "2024-01-02", "resolutiondate": "2024-01-05", "Status": "Closed", "Priority": "High"},
        {"Key": "B-3", "Created": "2024-01-03", "resolutiondate": "2024-01-04", "Status": "Rejected", "Priority": "Low"},
        {"Key": "B-4", "Created": "2024-01-04", "resolutiondate": "2024-01-05", "Status": "Cancelled", "Priority": "Low"},
        {"Key": "B-5", "Created": "2024-01-05", "resolutiondate": "2024-01-06", "Status": "Canceled", "Priority": "Low"},
        {"Key": "B-6", "Created": "2024-01-06", "resolutiondate": "2024-01-07", "Status": "Won't Fix", "Priority": "Low"},
    ])
    
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
                "rejected_statuses": ["Rejected", "Cancelled", "Canceled", "Won't Fix"],
            },
        },
        exclude_statuses=["Cancelled", "Canceled", "Won't Fix"],  # Exclude 3 out of 4 rejection types
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=data, llm_enabled=False)
    
    # Filtered data should only have 3 bugs (Open, Closed, Rejected)
    assert result.metadata["filtered_records"] == 3
    
    # But rejection_rate should see all 6 bugs
    rejection_result = result.metrics_results["rejection_rate"]
    rejection_summary = rejection_result.tables["rejection_summary"].iloc[0]
    
    assert rejection_summary["total"] == 6, f"Should see all 6 bugs, got {rejection_summary['total']}"
    assert rejection_summary["rejected"] == 4, f"Should count 4 rejected bugs, got {rejection_summary['rejected']}"
    assert rejection_summary["rejection_percent"] == 66.67, f"Should be 66.67% rejection rate, got {rejection_summary['rejection_percent']}"
    
    print("✓ Test passed: rejection_rate handles multiple excluded statuses")


if __name__ == "__main__":
    """Run tests manually."""
    print("=" * 70)
    print("Testing Rejection Rate with Status Exclusions")
    print("=" * 70)
    
    try:
        print("\n[1/3] Testing rejection_rate counts excluded statuses...")
        test_rejection_rate_counts_excluded_statuses()
        
        print("\n[2/3] Testing rejection_rate without exclusions...")
        test_rejection_rate_without_exclusions()
        
        print("\n[3/3] Testing rejection_rate with multiple excluded statuses...")
        test_rejection_rate_multiple_excluded_statuses()
        
        print("\n" + "=" * 70)
        print("✓ All tests PASSED!")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import sys
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)
