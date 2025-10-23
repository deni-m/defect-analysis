import pandas as pd
from .base import Metric, MetricResult

class CumulativeOpenClosed(Metric):
    id = "cumulative_open_closed"

    def compute(self, df: pd.DataFrame, cfg: dict) -> MetricResult:
        d = df.copy()
        # уніфікуємо дати
        d["created_at"]  = pd.to_datetime(d["created_at"],  errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
        d["resolved_at"] = pd.to_datetime(d["resolved_at"], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()

        opened = d.groupby("created_at").size().cumsum().rename("opened")
        closed = d.dropna(subset=["resolved_at"]).groupby("resolved_at").size().cumsum().rename("closed")
        # Forward-fill cumulative counts then replace remaining NaNs with 0
        trend = pd.concat([opened, closed], axis=1).ffill().fillna(0).astype(int)
        trend.index.name = "date"
        trend = trend.reset_index()

        summ = {
            "opened_cum": int(trend["opened"].iloc[-1]) if not trend.empty else 0,
            "closed_cum": int(trend["closed"].iloc[-1]) if not trend.empty else 0
        }

        return MetricResult(
            self.id,
            tables={"cumulative": trend, "summary": pd.DataFrame([summ])},
            summary=f"Opened={summ['opened_cum']}, Closed={summ['closed_cum']}"
        )

    def build_figure(self, result: MetricResult) -> str | None:
        import plotly.graph_objects as go
        trend = result.tables.get("cumulative")
        if trend is None or trend.empty or {"opened", "closed"}.issubset(trend.columns) is False:
            return None
        x = trend["date"] if "date" in trend.columns else trend.index
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=trend["opened"], mode="lines", name="Opened", fill="tozeroy"))
        fig.add_trace(go.Scatter(x=x, y=trend["closed"], mode="lines", name="Closed"))
        fig.update_layout(title="Cumulative Opened vs Closed")
        return fig.to_html(include_plotlyjs=False, full_html=False)
