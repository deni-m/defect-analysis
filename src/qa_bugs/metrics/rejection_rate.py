import pandas as pd
from .base import Metric, MetricResult


class RejectionRate(Metric):
    id = "rejection_rate"
    display_name = "Rejection Rate"

    def compute(self, df: pd.DataFrame, cfg: dict) -> MetricResult:
        d = df.copy()
        status_col = "status" if "status" in d.columns else None
        if status_col is None or d.empty:
            return MetricResult(
                self.id,
                tables={"rejection_summary": pd.DataFrame([{"rejected": 0, "total": 0, "rejection_percent": 0.0}])},
                summary="No data",
            )

        # Pull config-driven rejected statuses.
        # Path: cfg['metrics']['params']['rejection_rate']['rejected_statuses']
        metrics_cfg = cfg.get("metrics", {}).get("params", {})
        param_cfg = metrics_cfg.get(self.id, {}) if isinstance(metrics_cfg, dict) else {}
        raw_statuses = param_cfg.get("rejected_statuses", [])
        if not raw_statuses:
            # Fallback defaults (kept for backward compatibility / missing config)
            raw_statuses = ["Rejected", "Canceled", "Cancelled", "Won't Fix", "WONTFIX"]
        # Normalize for case-insensitive matching
        rejected_statuses_lower = {str(s).lower().strip() for s in raw_statuses if s is not None}

        d[status_col] = d[status_col].astype("string")
        total = int(len(d))
        rejected_mask = d[status_col].str.lower().isin(rejected_statuses_lower)
        rejected_count = int(rejected_mask.sum())
        pct = float(rejected_count / total * 100.0) if total > 0 else 0.0
        summary_row = {"rejected": rejected_count, "total": total, "rejection_percent": round(pct, 2)}
        return MetricResult(
            self.id,
            tables={"rejection_summary": pd.DataFrame([summary_row])},
            summary=f"Rejected={rejected_count} ({pct:.1f}%)",
        )

    def build_figure(self, result: MetricResult) -> str | None:
        """Create a simple rejection rate KPI display."""
        rejection_summary = result.tables.get("rejection_summary")
        if rejection_summary is None or rejection_summary.empty:
            return None

        row = rejection_summary.iloc[0]
        rejected = int(row.get("rejected", 0))
        total = int(row.get("total", 0))
        pct = float(row.get("rejection_percent", 0.0))

        # Create a simple KPI card display
        html = f"""
        <div style="display: flex; gap: 20px; padding: 15px; background-color: #f9f9f9; border-radius: 5px;">
            <div style="flex: 1; text-align: center; padding: 10px;">
                <div style="font-size: 28px; font-weight: bold; color: #d32f2f;">{pct:.1f}%</div>
                <div style="font-size: 12px; color: #666;">Rejection Rate</div>
            </div>
            <div style="flex: 1; text-align: center; padding: 10px;">
                <div style="font-size: 28px; font-weight: bold; color: #1976d2;">{rejected}</div>
                <div style="font-size: 12px; color: #666;">Rejected ({total} total)</div>
            </div>
        </div>
        """
        return html