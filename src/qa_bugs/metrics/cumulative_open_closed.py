import pandas as pd
from datetime import timedelta
from .base import Metric, MetricResult
from .defects_by_env_priority import DefectsByEnvPriority

class CumulativeOpenClosed(Metric):
    id = "cumulative_open_closed"
    display_name = "Cumulative Open vs Closed (Last 365 Days)"

    def compute(self, df: pd.DataFrame, cfg: dict) -> MetricResult:
        d = df.copy()
        
        # Validate required columns
        if "created_at" not in d.columns:
            return MetricResult(
                self.id,
                tables={"summary": pd.DataFrame([{"opened_cum": 0, "closed_cum": 0, "opened_hc_cum": 0, "closed_hc_cum": 0}])},
                summary="Missing required field: created_at",
                quality_notes=["Metric could not be calculated: required field 'created_at' is missing."],
            )
        
        # уніфікуємо дати
        d["created_at"]  = pd.to_datetime(d["created_at"],  errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
        
        # Check if resolved_at exists, if not create it as null column
        if "resolved_at" not in d.columns:
            d["resolved_at"] = pd.NaT
        else:
            d["resolved_at"] = pd.to_datetime(d["resolved_at"], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()

        # Filter for last 365 days based on created_at
        cutoff_date = d["created_at"].max() - timedelta(days=365)
        d_filtered = d[d["created_at"] >= cutoff_date].copy()

        trend = self._build_trend_table(d_filtered)

        prod_trend = pd.DataFrame()
        if "environment" in d_filtered.columns:
            d_env = d_filtered.copy()
            d_env["environment"] = d_env["environment"].apply(DefectsByEnvPriority._split_environment_value)
            d_env = d_env.explode("environment")
            d_env["environment"] = d_env["environment"].astype("string").str.strip().str.upper()
            d_prod = d_env[d_env["environment"].eq("PROD")].copy()
            prod_trend = self._build_trend_table(d_prod) if not d_prod.empty else pd.DataFrame()

        # Convert only numeric columns to int (preserve date column as datetime)
        for col in trend.columns:
            if col != "date":
                trend[col] = trend[col].astype(int)

        summ = {
            "opened_cum": int(trend["opened"].iloc[-1]) if not trend.empty else 0,
            "closed_cum": int(trend["closed"].iloc[-1]) if not trend.empty else 0,
            "opened_hc_cum": int(trend["opened_hc"].iloc[-1]) if not trend.empty else 0,
            "closed_hc_cum": int(trend["closed_hc"].iloc[-1]) if not trend.empty else 0,
            "prod_opened_cum": int(prod_trend["opened"].iloc[-1]) if not prod_trend.empty else 0,
            "prod_closed_cum": int(prod_trend["closed"].iloc[-1]) if not prod_trend.empty else 0,
            "prod_opened_hc_cum": int(prod_trend["opened_hc"].iloc[-1]) if not prod_trend.empty else 0,
            "prod_closed_hc_cum": int(prod_trend["closed_hc"].iloc[-1]) if not prod_trend.empty else 0,
        }

        # Create simplified LLM tables with both total and H+C summary
        # Daily table
        cumulative_daily = trend[["date", "opened", "closed", "opened_hc", "closed_hc"]].copy()
        cumulative_daily.columns = ["date", "total_opened", "total_closed", "hc_opened", "hc_closed"]

        # Weekly table (by week ending date)
        trend_with_week = trend.copy()
        trend_with_week["date"] = pd.to_datetime(trend_with_week["date"])
        trend_with_week["week_end"] = trend_with_week["date"] + pd.to_timedelta((6 - trend_with_week["date"].dt.dayofweek) % 7, unit="d")
        cumulative_weekly = trend_with_week.groupby("week_end")[["opened", "closed", "opened_hc", "closed_hc"]].last().reset_index()
        cumulative_weekly.columns = ["date", "total_opened", "total_closed", "hc_opened", "hc_closed"]

        # Monthly table (by month end date)
        trend_with_month = trend.copy()
        trend_with_month["date"] = pd.to_datetime(trend_with_month["date"])
        trend_with_month["month_end"] = trend_with_month["date"] + pd.offsets.MonthEnd(0)
        cumulative_monthly = trend_with_month.groupby("month_end")[["opened", "closed", "opened_hc", "closed_hc"]].last().reset_index()
        cumulative_monthly.columns = ["date", "total_opened", "total_closed", "hc_opened", "hc_closed"]

        return MetricResult(
            self.id,
            tables={
                "cumulative": trend,
                "prod_cumulative": prod_trend,
                "summary": pd.DataFrame([summ]),
                "cumulative_daily": cumulative_daily,
                "cumulative_weekly": cumulative_weekly,
                "cumulative_monthly": cumulative_monthly,
            },
            summary=f"Last 365 days — Total: Opened={summ['opened_cum']}, Closed={summ['closed_cum']} | High+Critical: Opened={summ['opened_hc_cum']}, Closed={summ['closed_hc_cum']}",
            llm_tables=["cumulative_daily", "cumulative_weekly", "cumulative_monthly"]
        )

    def _build_trend_table(self, df: pd.DataFrame) -> pd.DataFrame:
        opened = df.groupby("created_at").size().cumsum().rename("opened")
        closed = df.dropna(subset=["resolved_at"]).groupby("resolved_at").size().cumsum().rename("closed")
        trend = pd.concat([opened, closed], axis=1).ffill().fillna(0).astype(int)
        trend.index.name = "date"
        trend = trend.reset_index()

        if "priority" in df.columns:
            d_hc = df[df["priority"].map(self._is_high_or_critical_priority)].copy()
            opened_hc = d_hc.groupby("created_at").size().cumsum().rename("opened_hc")
            closed_hc = d_hc.dropna(subset=["resolved_at"]).groupby("resolved_at").size().cumsum().rename("closed_hc")
            trend_hc = pd.concat([opened_hc, closed_hc], axis=1).ffill().fillna(0).astype(int)
            trend_hc.index.name = "date"
            trend_hc = trend_hc.reset_index()
            trend = trend.merge(trend_hc, on="date", how="left")
            trend["opened_hc"] = trend["opened_hc"].ffill().fillna(0)
            trend["closed_hc"] = trend["closed_hc"].ffill().fillna(0)
        else:
            trend["opened_hc"] = 0
            trend["closed_hc"] = 0

        for col in trend.columns:
            if col != "date":
                trend[col] = trend[col].astype(int)
        return trend

    @staticmethod
    def _is_high_or_critical_priority(priority) -> bool:
        if pd.isna(priority):
            return False
        normalized = str(priority).strip().casefold()
        return any(token in normalized for token in ("critical", "highest", "high", "major", "p0", "p1"))

    def build_figure(self, result: MetricResult) -> str | None:
        trend = result.tables.get("cumulative")
        if trend is None or trend.empty or {"opened", "closed"}.issubset(trend.columns) is False:
            return None

        fig1 = self._build_open_closed_figure(trend, "All Defects")

        prod_trend = result.tables.get("prod_cumulative")
        fig2 = None
        if prod_trend is not None and not prod_trend.empty:
            fig2 = self._build_open_closed_figure(prod_trend, "PROD Defects")

        # Combine both charts vertically using HTML (hide modebar to prevent title overlap)
        html1 = fig1.to_html(include_plotlyjs=False, full_html=False, config={'displayModeBar': False})
        html2 = fig2.to_html(include_plotlyjs=False, full_html=False, config={'displayModeBar': False}) if fig2 is not None else ""

        combined_html = f"""
        <div style="display: flex; flex-direction: column; gap: 20px; width: 100%;">
            <div style="width: 100%;">
                {html1}
            </div>
            {f'<div style="width: 100%;">{html2}</div>' if html2 else ''}
        </div>
        """
        return combined_html

    def _build_open_closed_figure(self, trend: pd.DataFrame, title: str):
        import plotly.graph_objects as go
        x = trend["date"] if "date" in trend.columns else trend.index
        fig = go.Figure()
        trace_specs = [
            ("Opened", "opened", "#636efa", "solid", "tozeroy", "rgba(99,110,250,0.18)"),
            ("Closed", "closed", "#EF553B", "solid", "tozeroy", "rgba(239,85,59,0.35)"),
            ("Opened High+Critical", "opened_hc", "#636efa", "dash", None, None),
            ("Closed High+Critical", "closed_hc", "#EF553B", "dash", None, None),
        ]
        for name, column, color, dash, fill, fillcolor in trace_specs:
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=trend[column] if column in trend.columns else [0] * len(trend),
                    mode="lines",
                    name=name,
                    line=dict(width=2, color=color, dash=dash),
                    fill=fill,
                    fillcolor=fillcolor,
                )
            )
        fig.update_layout(
            title=title,
            height=400,
            margin=dict(l=50, r=50, t=64, b=50),
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
        )
        return fig
