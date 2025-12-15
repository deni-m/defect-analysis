import pandas as pd
from .base import Metric, MetricResult

class AgeByPriority(Metric):
    id = "age_by_priority"
    display_name = "Age by Priority"

    def compute(self, df: pd.DataFrame, cfg: dict) -> MetricResult:
        d = df.copy()
        d["created_at"]  = pd.to_datetime(d["created_at"],  errors="coerce", utc=True).dt.tz_convert(None)
        d["resolved_at"] = pd.to_datetime(d["resolved_at"], errors="coerce", utc=True).dt.tz_convert(None)

        now = pd.Timestamp.utcnow().tz_localize(None)
        end = d["resolved_at"].fillna(now)
        d["age_days"] = (end - d["created_at"]).dt.days

        grp = d.assign(priority=d["priority"].fillna("TBD")).groupby("priority")
        agg = grp["age_days"].agg(avg_age="mean", p50="median", count="count").reset_index()
        p90 = grp["age_days"].quantile(0.9).reset_index().rename(columns={"age_days":"p90"})
        agg = agg.merge(p90, on="priority", how="left")

        return MetricResult(
            self.id,
            tables={"age_by_priority": agg},
            summary="average/p50/p90 age by priority"
        )

    def build_figure(self, result: MetricResult) -> str | None:
        import plotly.express as px
        tbl = result.tables.get("age_by_priority")
        if tbl is None or tbl.empty or {"priority", "avg_age"}.issubset(tbl.columns) is False:
            return None
        fig = px.bar(
            tbl,
            x="priority",
            y="avg_age",
            title="Average Age by Priority (days)",
            color_discrete_sequence=["#5470C6"]  # Blue color
        )
        fig.update_layout(yaxis_title="avg_age (days)")
        return fig.to_html(include_plotlyjs=False, full_html=False)
