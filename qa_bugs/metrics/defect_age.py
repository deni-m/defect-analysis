import pandas as pd
from .base import Metric, MetricResult

class DefectAge(Metric):
    id = "defect_age"
    display_name = "Defect Age Distribution"

    def compute(self, df: pd.DataFrame, cfg: dict) -> MetricResult:
        d = df.copy()
        # 1) read as tz-aware (UTC), 2) remove tz -> becomes tz-naive
        d["created_at"]  = pd.to_datetime(d["created_at"],  errors="coerce", utc=True).dt.tz_convert(None)
        d["resolved_at"] = pd.to_datetime(d["resolved_at"], errors="coerce", utc=True).dt.tz_convert(None)

        # naive "now" in UTC
        now = pd.Timestamp.utcnow().tz_localize(None)

        end = d["resolved_at"].fillna(now)
        d["age_days"] = (end - d["created_at"]).dt.days

        stats = {
            "count": int(d.shape[0]),
            "avg_age": float(d["age_days"].dropna().mean()) if d["age_days"].notna().any() else 0.0,
            "p50": float(d["age_days"].dropna().median()) if d["age_days"].notna().any() else 0.0,
            "p90": float(d["age_days"].dropna().quantile(0.9)) if d["age_days"].notna().any() else 0.0,
        }

        tbl = d[["key", "status", "priority", "created_at", "resolved_at", "environment", "age_days"]]

        return MetricResult(
            self.id,
            tables={"defect_age": tbl, "stats": pd.DataFrame([stats])},
            summary=f"avg={stats['avg_age']:.1f}d, p50={stats['p50']:.0f}d, p90={stats['p90']:.0f}d, n={stats['count']}"
        )

    def build_figure(self, result: MetricResult) -> str | None:
        import plotly.express as px
        tbl = result.tables.get("defect_age")
        if tbl is None or tbl.empty or "age_days" not in tbl.columns:
            return None
        fig = px.histogram(tbl, x="age_days", nbins=20, title="Defect Age Distribution (days)")
        return fig.to_html(include_plotlyjs=False, full_html=False)
