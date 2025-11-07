import os
from pathlib import Path
import pandas as pd
import pytest
import subprocess

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
