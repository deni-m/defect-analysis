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
from qa_bugs.ingest.env_value_mapper import EnvironmentValueMapper
from qa_bugs.cli.html_report import HTMLReportGenerator
from qa_bugs.metrics import METRICS

# Load .env with override=True so .env file takes priority over system environment variables
load_dotenv(override=True)
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
    auto_map_env: bool = typer.Option(False, "--auto-map-env", help="Auto-map environment values to standard categories"),
    auto_classify: bool = typer.Option(False, "--auto-classify", help="Auto-classify statuses, priorities using AI"),
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

    # Handle environment value auto-mapping if enabled (CLI flag overrides config)
    auto_env_config = getattr(analysis_config, 'auto_env_mapping', None)
    if auto_map_env or (auto_env_config and auto_env_config.enabled):
        # First, normalize fields to access environment column
        from qa_bugs.ingest.normalizer import Normalizer
        normalizer_temp = Normalizer(
            analysis_config.fields_mapping,
            env_value_mapping=getattr(analysis_config, 'env_value_mapping', {})
        )
        df_temp = normalizer_temp.normalize(df_raw)
        
        if "environment" in df_temp.columns:
            # Get unique environment values
            unique_envs = df_temp["environment"].dropna().unique().tolist()
            
            if unique_envs:
                typer.echo("Auto-mapping environment values...")
                logging.info(f"Starting environment value mapping for {len(unique_envs)} unique values")
                
                # Initialize LLM service if needed
                llm_enabled = llm.lower() == "on" and analysis_config.llm.enabled
                llm_service = None
                
                if llm_enabled:
                    from qa_bugs.llm.service import LLMService
                    llm_dict = {
                        "enabled": True,
                        "prompts_dir": analysis_config.llm.prompts_dir,
                        "provider": analysis_config.llm.provider,
                        "endpoint": analysis_config.llm.endpoint,
                        "deployment": analysis_config.llm.deployment,
                        "api_version": analysis_config.llm.api_version,
                        "temperature": 0.1,
                        "max_tokens": 1000,
                        "debug": analysis_config.llm.debug,
                    }
                    llm_service = LLMService(llm_dict)
                
                # Get target categories from config
                target_categories = None
                allow_passthrough = True
                if auto_env_config:
                    target_categories = getattr(auto_env_config, 'target_categories', None)
                    allow_passthrough = getattr(auto_env_config, 'allow_passthrough', True)
                
                # Initialize environment mapper
                env_mapper = EnvironmentValueMapper(
                    llm_service=llm_service,
                    target_categories=target_categories
                )
                
                # Auto-map values
                env_result = env_mapper.auto_map_values(
                    unique_values=unique_envs,
                    allow_passthrough=allow_passthrough
                )
                
                # Check result
                if not env_result.success:
                    typer.echo("")
                    typer.secho(env_mapper.format_result_message(env_result), fg=typer.colors.RED)
                    typer.echo("")
                    typer.secho("❌ Environment value mapping failed", fg=typer.colors.RED)
                    raise typer.Exit(1)
                
                # Display mapping
                typer.echo("")
                typer.secho(f"[OK] Environment values mapped successfully ({env_result.method_used}):", fg=typer.colors.GREEN)
                for orig, mapped in sorted(env_result.value_mapping.items()):
                    if orig.upper() != mapped:  # Only show transformations
                        typer.echo(f"  {orig} -> {mapped}")
                
                # Show warnings if any
                if env_result.warnings:
                    typer.echo("")
                    typer.secho("[WARNING] Warnings:", fg=typer.colors.YELLOW)
                    for warning in env_result.warnings:
                        typer.echo(f"  - {warning}")
                
                typer.echo("")
                
                # Store mapping in config for normalizer
                if not hasattr(analysis_config, 'env_value_mapping'):
                    analysis_config.env_value_mapping = {}
                analysis_config.env_value_mapping.update(env_result.value_mapping)
        else:
            logging.warning("Environment column not found, skipping environment value mapping")

    # Handle auto-classification if enabled (CLI flag overrides config)
    if auto_classify or (hasattr(analysis_config, 'auto_classification') and analysis_config.auto_classification.enabled):
        typer.echo("AI data classification enabled - will analyze statuses and priorities...")
        logging.info("Auto-classification enabled via CLI flag or config")
        
        # Ensure auto_classification config exists
        if not hasattr(analysis_config, 'auto_classification'):
            from qa_bugs.services.models import AutoClassificationConfig
            analysis_config.auto_classification = AutoClassificationConfig(enabled=True)
        else:
            analysis_config.auto_classification.enabled = True

    # Run analysis using service
    typer.echo("Running analysis...")
    logging.info(f"Starting analysis: input={input}, since={since}, until={until}, llm={llm}")
    service = AnalysisService(analysis_config)

    missing_by_metric = service.check_metric_readiness(df_raw)
    if missing_by_metric:
        typer.echo("")
        typer.secho("⚠️  Some metrics will be skipped due to missing fields:", fg=typer.colors.YELLOW)
        for metric_id, fields in missing_by_metric.items():
            name = METRICS[metric_id].display_name if metric_id in METRICS else metric_id
            typer.echo(f"  - {name}: missing {', '.join(fields)}")
        typer.echo("")
        if not typer.confirm("Continue with the remaining metrics?"):
            raise typer.Exit(0)
        typer.echo("")

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

    # Use ASCII checkmark for Windows console compatibility
    checkmark = "[OK]"
    typer.echo(f"{checkmark} Analysis complete!")
    typer.echo(f"{checkmark} Report saved to: {out_path}")
    typer.echo(f"{checkmark} Logs saved to: {log_file}")
    typer.echo(f"{checkmark} Total records: {result.metadata['total_records']}")
    typer.echo(f"{checkmark} Filtered records: {result.metadata['filtered_records']}")
    typer.echo(f"{checkmark} Metrics computed: {len(result.metrics_results)}")


if __name__ == "__main__":
    app()
