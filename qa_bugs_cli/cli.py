"""CLI application for QA Bugs Analytics."""
import typer
import pandas as pd
import yaml
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from qa_bugs.services import AnalysisService, AnalysisConfig
from qa_bugs_cli.html_report import HTMLReportGenerator

load_dotenv()
app = typer.Typer(add_completion=False)


@app.command()
def run(
    config: Path = typer.Option(..., "--config", "-c", help="Path to YAML config"),
    input: Path = typer.Option(..., "--input", "-i", help="Path to input CSV"),
    since: str = typer.Option(None, "--since", help="YYYY-MM-DD filter (created since)"),
    until: str = typer.Option(None, "--until", help="YYYY-MM-DD filter (created until)"),
    llm: str = typer.Option("on", "--llm", help="on/off LLM analysis"),
    header_prefix: str = typer.Option(None, "--header-prefix", help="Optional prefix for report header"),
):
    """Run bug analytics analysis and generate HTML report."""
    # Load configuration
    config_dict = yaml.safe_load(config.read_text(encoding="utf-8"))
    analysis_config = AnalysisConfig.from_yaml_dict(config_dict)

    # Load CSV data
    df_raw = pd.read_csv(input)

    # Prepare output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path("output") / f"run_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Run analysis using service
    typer.echo("Running analysis...")
    service = AnalysisService(analysis_config)

    llm_enabled = llm.lower() == "on"
    result = service.run_analysis(
        df=df_raw,
        since=since,
        until=until,
        llm_enabled=llm_enabled,
        log_dir=str(out_dir)
    )

    # Generate HTML report
    typer.echo("Generating HTML report...")
    report_generator = HTMLReportGenerator()
    html = report_generator.generate(
        result=result,
        title=f"Bug Analytics Report {timestamp}",
        header_prefix=header_prefix,
        metric_order=analysis_config.enabled_metrics
    )

    # Save report
    out_path = out_dir / "report.html"
    out_path.write_text(html, encoding="utf-8")

    typer.echo(f"✓ Analysis complete!")
    typer.echo(f"✓ Report saved to: {out_path}")
    typer.echo(f"✓ Total records: {result.metadata['total_records']}")
    typer.echo(f"✓ Filtered records: {result.metadata['filtered_records']}")
    typer.echo(f"✓ Metrics computed: {len(result.metrics_results)}")


if __name__ == "__main__":
    app()
