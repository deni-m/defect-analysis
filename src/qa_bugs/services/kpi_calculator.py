"""KPI calculation logic - pure business logic, UI-agnostic."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

from qa_bugs.services.models import AnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class SummaryKPIs:
    """
    Pre-computed KPI values for AI Summary display.
    
    All counts and percentages are calculated from metric results.
    UI layers simply format and display these values.
    """
    # Core counts
    total_defects: Optional[int] = None
    opened_defects: Optional[int] = None
    closed_defects: Optional[int] = None
    
    # Calculated percentage
    open_pct: Optional[float] = None
    
    # Age metrics (days)
    avg_age_all: Optional[float] = None
    avg_age_closed: Optional[float] = None
    
    # Leakage
    leakage_pct: Optional[float] = None
    leaked_count: Optional[int] = None
    
    # Rejection
    rejection_pct: Optional[float] = None
    rejected_count: Optional[int] = None


def calculate_summary_kpis(result: AnalysisResult) -> SummaryKPIs:
    """
    Calculate summary KPIs from analysis results.
    
    Pure function: given AnalysisResult, returns computed KPIs.
    All business logic for extracting and deriving KPI values lives here.
    
    Args:
        result: AnalysisResult from AnalysisService
        
    Returns:
        SummaryKPIs with all computed values
    """
    kpis = SummaryKPIs()
    
    # Extract from each metric
    for metric_id, metric_result in result.metrics_results.items():
        if metric_id == "defect_age":
            _extract_defect_age_kpis(metric_result, kpis)
        elif metric_id == "cumulative_open_closed":
            _extract_cumulative_kpis(metric_result, kpis)
        elif metric_id == "leakage_rate":
            _extract_leakage_kpis(metric_result, kpis)
        elif metric_id == "rejection_rate":
            _extract_rejection_kpis(metric_result, kpis)
    
    # Derive calculated fields
    if kpis.total_defects and kpis.closed_defects is not None:
        open_count = kpis.total_defects - kpis.closed_defects
        if kpis.total_defects > 0:
            kpis.open_pct = round(open_count / kpis.total_defects * 100.0, 1)
    
    return kpis


def _extract_defect_age_kpis(metric_result, kpis: SummaryKPIs) -> None:
    """Extract KPIs from defect_age metric."""
    stats_tbl = metric_result.tables.get("stats")
    if stats_tbl is not None and not stats_tbl.empty:
        stats_row = stats_tbl.iloc[0].to_dict()
        
        # Core counts
        kpis.total_defects = int(stats_row.get("count", 0))
        kpis.avg_age_all = float(stats_row.get("avg_age", 0.0))
        
        # Prefer stats-based closed age and open/closed counts (all-time)
        avg_closed_val = stats_row.get("avg_age_closed")
        if avg_closed_val is not None:
            try:
                kpis.avg_age_closed = float(avg_closed_val)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to convert avg_age_closed to float: {avg_closed_val} - {e}")
        
        open_count_val = stats_row.get("open_count")
        closed_count_val = stats_row.get("closed_count")
        if open_count_val is not None and closed_count_val is not None:
            try:
                kpis.opened_defects = int(open_count_val)
                kpis.closed_defects = int(closed_count_val)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to convert open/closed counts to int: open={open_count_val}, closed={closed_count_val} - {e}")
    
    # Backward-compatible fallback: derive from defect_age table
    if (kpis.opened_defects is None or kpis.closed_defects is None) or kpis.avg_age_closed is None:
        tbl = metric_result.tables.get("defect_age")
        if tbl is not None and not tbl.empty and {"resolved_at", "age_days"}.issubset(tbl.columns):
            closed_mask = tbl["resolved_at"].notna()
            open_mask = tbl["resolved_at"].isna()
            
            if kpis.closed_defects is None:
                kpis.closed_defects = int(closed_mask.sum())
            if kpis.opened_defects is None:
                kpis.opened_defects = int(open_mask.sum())
            
            if kpis.avg_age_closed is None and closed_mask.any():
                try:
                    kpis.avg_age_closed = float(tbl.loc[closed_mask, "age_days"].mean())
                except (TypeError, ValueError) as e:
                    logger.warning(f"Failed to calculate avg_age_closed from defect_age table - {e}")


def _extract_cumulative_kpis(metric_result, kpis: SummaryKPIs) -> None:
    """Extract KPIs from cumulative_open_closed metric (fallback only)."""
    # Only use cumulative metric as a fallback when defect_age stats
    # are unavailable. Cumulative metric is 365-day window, so we
    # avoid overriding all-time stats computed above.
    if kpis.opened_defects is None or kpis.closed_defects is None:
        summary_tbl = metric_result.tables.get("summary")
        if summary_tbl is not None and not summary_tbl.empty:
            row = summary_tbl.iloc[0].to_dict()
            try:
                kpis.opened_defects = int(row.get("opened_cum", 0))
                kpis.closed_defects = int(row.get("closed_cum", 0))
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to convert cumulative counts to int: opened={row.get('opened_cum')}, closed={row.get('closed_cum')} - {e}")
            
            if kpis.total_defects is None:
                kpis.total_defects = kpis.opened_defects


def _extract_leakage_kpis(metric_result, kpis: SummaryKPIs) -> None:
    """Extract KPIs from leakage_rate metric."""
    overall_tbl = metric_result.tables.get("leakage_overall")
    legacy_tbl = metric_result.tables.get("leakage_overall_kpis")
    row = None
    if overall_tbl is not None and not overall_tbl.empty:
        row = overall_tbl.iloc[0].to_dict()
    elif legacy_tbl is not None and not legacy_tbl.empty:
        row = legacy_tbl.iloc[0].to_dict()
    
    if row:
        # Handle various column name aliases
        rate = None
        for key in ["rate_percent", "leakage_percent", "leakage"]:
            if key in row and row[key] is not None:
                rate = row[key]
                break
        
        leaked_v = None
        for key in ["leaked", "leaked_count"]:
            if key in row and row[key] is not None:
                leaked_v = row[key]
                break
        
        total_v = None
        for key in ["total", "total_considered"]:
            if key in row and row[key] is not None:
                total_v = row[key]
                break
        
        kpis.leakage_pct = float(rate) if isinstance(rate, (int, float)) else None
        kpis.leaked_count = int(leaked_v) if isinstance(leaked_v, (int, float)) else None
        if kpis.total_defects is None and isinstance(total_v, (int, float)):
            kpis.total_defects = int(total_v)


def _extract_rejection_kpis(metric_result, kpis: SummaryKPIs) -> None:
    """Extract KPIs from rejection_rate metric."""
    rej_tbl = metric_result.tables.get("rejection_summary")
    if rej_tbl is None or rej_tbl.empty:
        alt_tbl = metric_result.tables.get("summary")
        if alt_tbl is not None and not alt_tbl.empty:
            rej_tbl = alt_tbl
    
    if rej_tbl is not None and not rej_tbl.empty:
        rej_row = rej_tbl.iloc[0].to_dict()
        kpis.rejection_pct = float(rej_row.get("rejection_percent", 0)) if isinstance(
            rej_row.get("rejection_percent"), (int, float)
        ) else None
        rejected_val = rej_row.get("rejected", 0)
        total_val = rej_row.get("total", None)
        kpis.rejected_count = int(rejected_val) if isinstance(rejected_val, (int, float)) else None
        if kpis.total_defects is None and isinstance(total_val, (int, float)):
            kpis.total_defects = int(total_val)
