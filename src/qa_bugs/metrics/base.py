# qa_bugs/metrics/base.py
from typing import Dict, Any
import pandas as pd
import numpy as np
from datetime import datetime, date

def _to_jsonable(v):
    # NaN / NaT / <NA>
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        if pd.isna(v):   # покриває pd.NaT, pd.NA, NaN
            return None
    except Exception:
        pass

    # Дати/час
    if isinstance(v, (pd.Timestamp, datetime, date)):
        # перетворимо на ISO-рядок
        try:
            return pd.to_datetime(v).to_pydatetime().isoformat()
        except Exception:
            return str(v)

    # NumPy типи → вбудовані
    if isinstance(v, (np.integer, )):
        return int(v)
    if isinstance(v, (np.floating, )):
        if np.isnan(v):
            return None
        return float(v)
    if isinstance(v, (np.bool_, )):
        return bool(v)

    # решта як є (str, int, float, bool, dict, list)
    return v

def _df_to_records_json_safe(df: pd.DataFrame):
    records = df.to_dict(orient="records")
    safe_records = []
    for row in records:
        safe_records.append({k: _to_jsonable(v) for k, v in row.items()})
    return safe_records


class MetricResult:
    def __init__(self, metric_id: str, tables: Dict[str, pd.DataFrame] = None, charts: Dict[str, Any] = None, summary: str = "", llm_tables: list[str] = None, quality_notes: list[str] = None, skip_report: bool = False):
        self.metric_id = metric_id
        self.tables = tables or {}
        self.charts = charts or {}
        self.summary = summary
        # Optional list of table names to include in LLM payload (defaults to all)
        self.llm_tables = llm_tables
        # Data quality warnings forwarded to LLM context
        self.quality_notes = quality_notes or []
        # Optional metrics can set this when there is no meaningful data to show.
        self.skip_report = skip_report

    def payload(self) -> dict:
        # If llm_tables is specified, only include those tables; otherwise include all
        tables_to_include = self.llm_tables if self.llm_tables is not None else list(self.tables.keys())
        result = {
            "metric_id": self.metric_id,
            "summary": self.summary,
            "tables": {
                name: _df_to_records_json_safe(self.tables[name])
                for name in tables_to_include
                if name in self.tables
            },
        }
        if self.quality_notes:
            result["data_quality_warnings"] = self.quality_notes
        return result

class Metric:
    id: str = "base"
    # Human-friendly name for report headings; ReportBuilder will prefer this when present.
    display_name: str = "Base Metric"
    def compute(self, df: pd.DataFrame, cfg: dict) -> MetricResult:
        raise NotImplementedError

    def build_figure(self, result: MetricResult) -> str | None:
        """Return HTML fragment (Plotly figure or composed block) for the metric.

        Default: None (metric produces no figure). Concrete metrics override.
        The ReportBuilder will call this instead of hard-coding metric ids.
        """
        return None
