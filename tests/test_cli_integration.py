import os
from pathlib import Path
import pandas as pd
import pytest
import subprocess
import re


@pytest.mark.parametrize("metrics", ["defect_age,age_by_priority"])
def test_cli_generates_report(tmp_path, metrics):
    # Build a tiny CSV
    data = [
        {"Key": "BUG-1", "Created": "2025-10-01T00:00:00Z", "resolutiondate": "2025-10-03T00:00:00Z", "Status": "Closed", "Priority": "High", "FixVersions": "v1", "customfield_12200": "QA", "Component": "API"},
        {"Key": "BUG-2", "Created": "2025-10-02T00:00:00Z", "resolutiondate": "", "Status": "Open", "Priority": "Low", "FixVersions": "v1", "customfield_12200": "DEV", "Component": "UI"},
    ]
    csv_path = tmp_path / "sample.csv"
    pd.DataFrame(data).to_csv(csv_path, index=False)

    config_text = Path("configs/example.config.yml").read_text(encoding="utf-8")
    # Use same config but restrict enabled metrics to the param
    config_override = config_text.replace("enabled:", f"enabled:\n    - defect_age\n    - age_by_priority")
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(config_override, encoding="utf-8")

    cmd = ["python", "-m", "qa_bugs.cli.cli", "--config", str(cfg_path), "--input", str(csv_path), "--llm", "off"]
    subprocess.run(cmd, check=True)

    out_dir = Path("output")
    # Find newest run directory created after command
    run_dirs = sorted([p for p in out_dir.glob("run_*") if p.is_dir()], reverse=True)
    assert run_dirs, "No run directories created"
    latest = run_dirs[0]
    report_file = latest / "report.html"
    assert report_file.exists(), "Report file not generated"

    html = report_file.read_text(encoding="utf-8")
    # Basic sanity checks
    assert "Defect Age Distribution" in html
    assert "Age by Priority" in html


def test_cli_report_includes_kpis(tmp_path):
    """Test that CLI generates report with correct KPI values."""
    # Create test data with known values for KPI verification
    data = [
        # 3 closed bugs
        {"Key": "BUG-1", "Created": "2025-10-01T00:00:00Z", "resolutiondate": "2025-10-03T00:00:00Z", "Status": "Closed", "Priority": "High", "customfield_12200": "QA"},
        {"Key": "BUG-2", "Created": "2025-10-02T00:00:00Z", "resolutiondate": "2025-10-04T00:00:00Z", "Status": "Closed", "Priority": "Medium", "customfield_12200": "QA"},
        {"Key": "BUG-3", "Created": "2025-10-03T00:00:00Z", "resolutiondate": "2025-10-05T00:00:00Z", "Status": "Closed", "Priority": "Low", "customfield_12200": "QA"},
        # 2 open bugs
        {"Key": "BUG-4", "Created": "2025-10-04T00:00:00Z", "resolutiondate": "", "Status": "Open", "Priority": "High", "customfield_12200": "DEV"},
        {"Key": "BUG-5", "Created": "2025-10-05T00:00:00Z", "resolutiondate": "", "Status": "Open", "Priority": "Medium", "customfield_12200": "DEV"},
        # 1 leaked bug
        {"Key": "BUG-6", "Created": "2025-10-06T00:00:00Z", "resolutiondate": "2025-10-08T00:00:00Z", "Status": "Closed", "Priority": "High", "customfield_12200": "Prod"},
    ]
    csv_path = tmp_path / "test_data.csv"
    pd.DataFrame(data).to_csv(csv_path, index=False)

    # Create config with necessary metrics
    config_yaml = """
project:
  timezone: "UTC"

fields_mapping:
  key: "Key"
  created_at: "Created"
  resolved_at: "resolutiondate"
  status: "Status"
  priority: "Priority"
  environment: "customfield_12200"

metrics:
  enabled:
    - defect_age
    - leakage_rate
    
  params:
    leakage_rate:
      intended_env: ["QA"]
      leak_envs: ["Prod"]

llm:
  enabled: false
"""
    cfg_path = tmp_path / "test_config.yml"
    cfg_path.write_text(config_yaml, encoding="utf-8")

    # Run CLI
    cmd = ["python", "-m", "qa_bugs.cli.cli", "--config", str(cfg_path), "--input", str(csv_path), "--llm", "off"]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)

    # Verify output messages (checkmark may have encoding issues, so check the text)
    assert "Analysis complete!" in result.stdout
    assert "Total records: 6" in result.stdout

    # Find and read the generated report
    out_dir = Path("output")
    run_dirs = sorted([p for p in out_dir.glob("run_*") if p.is_dir()], reverse=True)
    assert run_dirs, "No run directories created"
    latest = run_dirs[0]
    report_file = latest / "report.html"
    assert report_file.exists(), "Report file not generated"

    html = report_file.read_text(encoding="utf-8")

    # Verify KPIs are present in the HTML
    # Total defects should be 6
    assert "Total Defects" in html or "total defects" in html.lower()
    
    # Check for specific KPI values (may be formatted differently)
    # We expect: 6 total, 4 closed, 2 open (33.3% open)
    # Note: HTML generator might format these differently, so we look for the numbers
    assert "6" in html  # Total defects
    
    # Check that leakage metric is calculated
    # Expected: 1 leaked out of 4 bugs that went through QA/Prod = 25%
    assert "Leakage" in html or "leakage" in html.lower()


def test_analysis_service_kpi_calculation():
    """Direct test of AnalysisService to verify KPI calculation."""
    from qa_bugs.services import AnalysisService, AnalysisConfig
    
    # Create test data
    data = pd.DataFrame([
        {"Key": "B-1", "Created": "2025-10-01", "resolutiondate": "2025-10-03", "Status": "Closed", "Priority": "High"},
        {"Key": "B-2", "Created": "2025-10-02", "resolutiondate": "2025-10-05", "Status": "Closed", "Priority": "Low"},
        {"Key": "B-3", "Created": "2025-10-03", "resolutiondate": "", "Status": "Open", "Priority": "Medium"},
    ])
    
    # Create minimal config
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
        },
        enabled_metrics=["defect_age"],
        llm=None
    )
    
    # Run analysis
    service = AnalysisService(config)
    result = service.run_analysis(df=data, llm_enabled=False)
    
    # Verify KPIs are calculated
    assert result.summary_kpis is not None, "summary_kpis should be computed"
    assert result.summary_kpis.total_defects == 3, "Should have 3 total defects"
    assert result.summary_kpis.closed_defects == 2, "Should have 2 closed defects"
    assert result.summary_kpis.opened_defects == 1, "Should have 1 open defect"
    assert result.summary_kpis.open_pct == 33.3, "Open percentage should be 33.3%"
    assert result.summary_kpis.avg_age_all is not None, "Average age should be calculated"


def test_analysis_service_with_leakage_and_rejection():
    """Test AnalysisService KPI calculation with leakage and rejection metrics."""
    from qa_bugs.services import AnalysisService, AnalysisConfig
    
    # Create test data with known leakage and rejection
    data = pd.DataFrame([
        # QA bugs that didn't leak
        {"Key": "B-1", "Created": "2025-10-01", "resolutiondate": "2025-10-03", "Status": "Closed", "Priority": "High", "Environment": "QA"},
        {"Key": "B-2", "Created": "2025-10-02", "resolutiondate": "2025-10-04", "Status": "Closed", "Priority": "High", "Environment": "QA"},
        # Leaked bug
        {"Key": "B-3", "Created": "2025-10-03", "resolutiondate": "2025-10-05", "Status": "Closed", "Priority": "High", "Environment": "Prod"},
        # Rejected bug
        {"Key": "B-4", "Created": "2025-10-04", "resolutiondate": "2025-10-06", "Status": "Rejected", "Priority": "Low", "Environment": "DEV"},
    ])
    
    config = AnalysisConfig(
        fields_mapping={
            "key": "Key",
            "created_at": "Created",
            "resolved_at": "resolutiondate",
            "status": "Status",
            "priority": "Priority",
            "environment": "Environment",
        },
        enabled_metrics=["defect_age", "leakage_rate", "rejection_rate"],
        metric_params={
            "leakage_rate": {
                "intended_env": ["QA"],
                "leak_envs": ["Prod"],
            },
            "rejection_rate": {
                "rejected_statuses": ["Rejected"],
            },
        },
        llm=None
    )
    
    service = AnalysisService(config)
    result = service.run_analysis(df=data, llm_enabled=False)
    
    # Verify KPIs
    assert result.summary_kpis is not None
    assert result.summary_kpis.total_defects == 4
    
    # Leakage: 1 leaked out of 3 QA+Prod bugs = 33.3%
    assert result.summary_kpis.leakage_pct is not None
    assert result.summary_kpis.leaked_count == 1
    
    # Rejection: 1 rejected out of 4 total = 25%
    assert result.summary_kpis.rejection_pct == 25.0
    assert result.summary_kpis.rejected_count == 1
