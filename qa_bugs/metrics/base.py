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
    def __init__(self, metric_id: str, tables: Dict[str, pd.DataFrame] = None, charts: Dict[str, Any] = None, summary: str = ""):
        self.metric_id = metric_id
        self.tables = tables or {}
        self.charts = charts or {}
        self.summary = summary

    def payload(self) -> dict:
        return {
            "metric_id": self.metric_id,
            "summary": self.summary,
            "tables": {
                name: _df_to_records_json_safe(df) for name, df in self.tables.items()
            },
        }

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
