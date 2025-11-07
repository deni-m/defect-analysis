import typer
import pandas as pd
import yaml
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from qa_bugs.ingest.normalizer import Normalizer
from qa_bugs.ingest.filters import apply_filters
from qa_bugs.metrics import METRICS
from qa_bugs.report.builder import ReportBuilder
from qa_bugs.llm.service import LLMService

load_dotenv()
app = typer.Typer(add_completion=False)

@app.command()
def run(
    config: Path = typer.Option(..., "--config", "-c", help="Path to YAML config"),
    input: Path = typer.Option(..., "--input", "-i", help="Path to input CSV"),
    since: str = typer.Option(None, "--since", help="YYYY-MM-DD filter (created since)"),
    until: str = typer.Option(None, "--until", help="YYYY-MM-DD filter (created until)"),
    llm: str = typer.Option("off", "--llm", help="on/off LLM analysis"),
    header_prefix: str = typer.Option(None, "--header-prefix", help="Optional prefix for report header"),  # NEW
):
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))

    df_raw = pd.read_csv(input)

    norm = Normalizer(mapping=cfg.get("fields_mapping", {}))
    df_norm = norm.normalize(df_raw)

    df_f = apply_filters(
        df_norm,
        since=since,
        until=until,
        exclude_statuses=cfg.get("exclude_statuses", [])
    )

    # Metrics now sourced exclusively from config (static set)
    metric_ids = cfg['metrics']['enabled']
    results = {}
    metrics_params_root = cfg.get("metrics", {}).get("params", {})
    common_params = metrics_params_root.get("common", {})
    for metric_id in metric_ids:
        metric_cls = METRICS[metric_id]
        specific = metrics_params_root.get(metric_id, {})
        # Merge common + specific (specific overrides)
        merged_params = {**common_params, **specific}
        # Provide fallback access to original full config if a legacy metric needs it
        merged_params["__full_config__"] = cfg
        res = metric_cls().compute(df_f, merged_params)
        results[metric_id] = res

    llm_cfg = cfg.get("llm", {})
    llm_enabled = (llm.lower() == "on") and llm_cfg.get("enabled", True)
    insights = {}
    overall = ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path("output") / f"run_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if llm_enabled:
        service = LLMService(llm_cfg, log_dir=str(out_dir))
        for metric_id, res in results.items():
            insights[metric_id] = service.analyze_metric(metric_id, res.payload())
        # Summarize based on generated insight texts instead of raw metric payloads
        overall = service.summarize_texts(insights)

    out_path = out_dir / "report.html"

    builder = ReportBuilder()
    html = builder.build(
        results=results,
        insights=insights,
        overall=overall,
        title=f"Bug Analytics Report {timestamp}",
        metric_order=metric_ids,
        header_prefix=header_prefix,  # NEW
    )
    out_path.write_text(html, encoding="utf-8")
    typer.echo(f"Report saved to: {out_path}")

if __name__ == "__main__":
    app()
