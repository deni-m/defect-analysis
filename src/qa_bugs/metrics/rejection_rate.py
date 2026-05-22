import pandas as pd
from .base import Metric, MetricResult


class RejectionRate(Metric):
    id = "rejection_rate"
    display_name = "Rejection Rate"

    # Default rejected resolution/status values (case-insensitive)
    DEFAULT_REJECTED_RESOLUTIONS = [
        "Rejected", "Canceled", "Cancelled", "Won't Fix", "WONTFIX",
        "Duplicate", "Invalid", "Cannot Reproduce", "Won't Do",
    ]
    DEFAULT_REJECTED_STATUSES = [
        "Rejected", "Canceled", "Cancelled", "Won't Fix", "WONTFIX",
    ]

    def compute(self, df: pd.DataFrame, cfg: dict, profile=None) -> MetricResult:
        d = df.copy()

        has_status = "status" in d.columns
        has_resolution = "resolution" in d.columns

        if not has_status and not has_resolution or d.empty:
            reason = "no status column found" if not d.empty else "empty dataset"
            return MetricResult(
                self.id,
                tables={"rejection_summary": pd.DataFrame([{"rejected": 0, "total": 0, "rejection_percent": 0.0}])},
                summary="No data",
                quality_notes=[f"Metric could not be calculated: {reason}."],
            )

        metrics_cfg = cfg.get("metrics", {}).get("params", {})
        param_cfg = metrics_cfg.get(self.id, {}) if isinstance(metrics_cfg, dict) else {}

        # Resolution-first: if resolution column exists, use it exclusively.
        # Otherwise fall back to status column.
        if has_resolution:
            eval_col = "resolution"
            raw_values = (
                param_cfg.get("rejected_resolutions", [])
                or self._profile_rejected_resolutions(profile)
                or self.DEFAULT_REJECTED_RESOLUTIONS
            )
        else:
            eval_col = "status"
            raw_values = (
                param_cfg.get("rejected_statuses", [])
                or param_cfg.get("rejected_resolutions", [])
                or self.DEFAULT_REJECTED_STATUSES
            )

        rejected_lower = {str(s).lower().strip() for s in raw_values if s is not None}

        d[eval_col] = d[eval_col].astype("string")
        total = int(len(d))
        rejected_mask = d[eval_col].str.lower().str.strip().isin(rejected_lower)
        rejected_count = int(rejected_mask.sum())
        pct = float(rejected_count / total * 100.0) if total > 0 else 0.0
        summary_row = {"rejected": rejected_count, "total": total, "rejection_percent": round(pct, 2)}
        return MetricResult(
            self.id,
            tables={"rejection_summary": pd.DataFrame([summary_row])},
            summary=f"Rejected={rejected_count} ({pct:.1f}%)",
        )

    @staticmethod
    def _profile_rejected_resolutions(profile) -> list:
        if not profile or not getattr(profile, "resolution_profile", None):
            return []
        return getattr(profile.resolution_profile, "rejected_resolutions", []) or []

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
