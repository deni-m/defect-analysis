"""CLI application for QA Bugs Analytics."""
import typer
import pandas as pd
import yaml
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from qa_bugs.services import AnalysisService, AnalysisConfig
from qa_bugs.ingest.field_mapper import FieldMappingService
from qa_bugs.cli.html_report import HTMLReportGenerator

load_dotenv()
app = typer.Typer(add_completion=False)


def setup_logging(log_dir: Path, level: int = logging.INFO):
    """Configure logging to file and console."""
    # Create logs directory
    log_file = log_dir / "qa_bugs.log"
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )
    
    # File handler - detailed logs
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    
    # Console handler - only INFO and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Log startup
    logging.info(f"Logging initialized. Log file: {log_file}")
    
    return log_file


@app.command()
def run(
    config: Path = typer.Option(..., "--config", "-c", help="Path to YAML config"),
    input: Path = typer.Option(..., "--input", "-i", help="Path to input CSV"),
    since: str = typer.Option(None, "--since", help="YYYY-MM-DD filter (created since)"),
    until: str = typer.Option(None, "--until", help="YYYY-MM-DD filter (created until)"),
    llm: str = typer.Option("on", "--llm", help="on/off LLM analysis"),
    auto_map: bool = typer.Option(False, "--auto-map", help="Auto-detect field mapping using LLM"),
    header_prefix: str = typer.Option(None, "--header-prefix", help="Optional prefix for report header"),
):
    """Run bug analytics analysis and generate HTML report."""
    # Prepare output directory early for logging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path("output") / f"run_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup logging to file early
    log_file = setup_logging(out_dir, level=logging.INFO)
    
    # Load configuration
    config_dict = yaml.safe_load(config.read_text(encoding="utf-8"))
    analysis_config = AnalysisConfig.from_yaml_dict(config_dict)

    # Load CSV data
    df_raw = pd.read_csv(input)

    # Handle auto-mapping if enabled (CLI flag overrides config)
    if auto_map or analysis_config.auto_mapping.enabled:
        typer.echo("Auto-detecting field mapping...")
        logging.info("Starting auto field mapping detection")
        
        # Initialize LLM service if needed
        llm_enabled = llm.lower() == "on" and analysis_config.llm.enabled
        llm_service = None
        
        if llm_enabled:
            from qa_bugs.llm.service import LLMService
            # Convert config to dict format for LLMService
            llm_dict = {
                "enabled": True,
                "prompts_dir": analysis_config.llm.prompts_dir,
                "provider": analysis_config.llm.provider,
                "endpoint": analysis_config.llm.endpoint,
                "deployment": analysis_config.llm.deployment,
                "api_version": analysis_config.llm.api_version,
                "temperature": 0.1,  # Lower temperature for mapping task
                "max_tokens": 1000,
                "debug": analysis_config.llm.debug,
            }
            llm_service = LLMService(llm_dict)
        
        # Initialize field mapping service
        field_mapper = FieldMappingService(llm_service=llm_service)
        
        # Auto-detect mapping
        validation_result = field_mapper.auto_detect_mapping(
            df=df_raw,
            sample_rows=analysis_config.auto_mapping.sample_rows
        )
        
        # Check validation
        if not validation_result.valid:
            typer.echo("")
            typer.secho(field_mapper.format_validation_error(validation_result), fg=typer.colors.RED)
            typer.echo("")
            typer.secho("❌ Cannot proceed without valid field mapping", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        # Display detected mapping
        typer.echo("")
        typer.secho("[OK] Field mapping detected successfully:", fg=typer.colors.GREEN)
        for canonical, csv_col in validation_result.mapping.items():
            typer.echo(f"  {canonical} -> {csv_col}")
        
        # Show warnings if any
        if validation_result.warnings:
            typer.echo("")
            typer.secho("[WARNING] Warnings:", fg=typer.colors.YELLOW)
            for warning in validation_result.warnings:
                typer.echo(f"  - {warning}")
        
        typer.echo("")
        
        # Override config with detected mapping
        analysis_config.fields_mapping = validation_result.mapping

    # Run analysis using service
    typer.echo("Running analysis...")
    logging.info(f"Starting analysis: input={input}, since={since}, until={until}, llm={llm}")
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
    
    logging.info(f"Analysis complete. Report saved to: {out_path}")
    logging.info(f"Logs saved to: {log_file}")

    typer.echo(f"✓ Analysis complete!")
    typer.echo(f"✓ Report saved to: {out_path}")
    typer.echo(f"✓ Logs saved to: {log_file}")
    typer.echo(f"✓ Total records: {result.metadata['total_records']}")
    typer.echo(f"✓ Filtered records: {result.metadata['filtered_records']}")
    typer.echo(f"✓ Metrics computed: {len(result.metrics_results)}")


if __name__ == "__main__":
    app()
