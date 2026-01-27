import pandas as pd
from datetime import timedelta
from .base import Metric, MetricResult

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
                summary="Missing required field: created_at"
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

        # Total cumulative (all defects)
        opened = d_filtered.groupby("created_at").size().cumsum().rename("opened")
        closed = d_filtered.dropna(subset=["resolved_at"]).groupby("resolved_at").size().cumsum().rename("closed")
        # Forward-fill cumulative counts then replace remaining NaNs with 0
        trend = pd.concat([opened, closed], axis=1).ffill().fillna(0).astype(int)
        trend.index.name = "date"
        trend = trend.reset_index()

        # High+Critical subset (only if priority column exists)
        if "priority" in d_filtered.columns:
            d_hc = d_filtered[d_filtered["priority"].isin(["High", "Critical"])].copy()
            opened_hc = d_hc.groupby("created_at").size().cumsum().rename("opened_hc")
            closed_hc = d_hc.dropna(subset=["resolved_at"]).groupby("resolved_at").size().cumsum().rename("closed_hc")
            trend_hc = pd.concat([opened_hc, closed_hc], axis=1).ffill().fillna(0).astype(int)
            trend_hc.index.name = "date"
            trend_hc = trend_hc.reset_index()

            # Merge H+C data into main trend table, forward-filling H+C values across all dates
            trend = trend.merge(trend_hc, on="date", how="left")
            # Forward-fill H+C columns to maintain last known values, then fill remaining with 0
            trend["opened_hc"] = trend["opened_hc"].ffill().fillna(0)
            trend["closed_hc"] = trend["closed_hc"].ffill().fillna(0)
        else:
            # If priority doesn't exist, create zero columns
            trend["opened_hc"] = 0
            trend["closed_hc"] = 0

        # Convert only numeric columns to int (preserve date column as datetime)
        for col in trend.columns:
            if col != "date":
                trend[col] = trend[col].astype(int)

        summ = {
            "opened_cum": int(trend["opened"].iloc[-1]) if not trend.empty else 0,
            "closed_cum": int(trend["closed"].iloc[-1]) if not trend.empty else 0,
            "opened_hc_cum": int(trend["opened_hc"].iloc[-1]) if not trend.empty else 0,
            "closed_hc_cum": int(trend["closed_hc"].iloc[-1]) if not trend.empty else 0,
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
            tables={"cumulative": trend, "summary": pd.DataFrame([summ]), "cumulative_daily": cumulative_daily, "cumulative_weekly": cumulative_weekly, "cumulative_monthly": cumulative_monthly},
            summary=f"Last 365 days — Total: Opened={summ['opened_cum']}, Closed={summ['closed_cum']} | High+Critical: Opened={summ['opened_hc_cum']}, Closed={summ['closed_hc_cum']}",
            llm_tables=["cumulative_daily", "cumulative_weekly", "cumulative_monthly"]
        )

    def build_figure(self, result: MetricResult) -> str | None:
        import plotly.graph_objects as go
        trend = result.tables.get("cumulative")
        if trend is None or trend.empty or {"opened", "closed"}.issubset(trend.columns) is False:
            return None
        x = trend["date"] if "date" in trend.columns else trend.index

        # Chart 1: Total defects
        fig1 = go.Figure()
        fig1.add_trace(
            go.Scatter(
                x=x,
                y=trend["opened"],
                mode="lines",
                name="Opened",
                fill="tozeroy",
                line=dict(width=2, color="#636efa"),
            )
        )
        fig1.add_trace(
            go.Scatter(
                x=x,
                y=trend["closed"],
                mode="lines",
                name="Closed",
                fill="tozeroy",
                line=dict(width=2, color="#EF553B"),
                fillcolor="rgba(239,85,59,0.35)",
            )
        )
        fig1.update_layout(
            title="Total Defects",
            height=400,
            margin=dict(l=50, r=50, t=50, b=50)
        )

        # Chart 2: High+Critical subset
        fig2 = go.Figure()
        if "opened_hc" in trend.columns and "closed_hc" in trend.columns:
            fig2.add_trace(
                go.Scatter(
                    x=x,
                    y=trend["opened_hc"],
                    mode="lines",
                    name="Opened",
                    fill="tozeroy",
                    line=dict(width=2, color="#636efa"),
                )
            )
            fig2.add_trace(
                go.Scatter(
                    x=x,
                    y=trend["closed_hc"],
                    mode="lines",
                    name="Closed",
                    fill="tozeroy",
                    line=dict(width=2, color="#EF553B"),
                    fillcolor="rgba(239,85,59,0.35)",
                )
            )
        fig2.update_layout(
            title="High + Critical Defects",
            height=400,
            margin=dict(l=50, r=50, t=50, b=50)
        )

        # Combine both charts vertically using HTML (hide modebar to prevent title overlap)
        html1 = fig1.to_html(include_plotlyjs=False, full_html=False, config={'displayModeBar': False})
        html2 = fig2.to_html(include_plotlyjs=False, full_html=False, config={'displayModeBar': False})

        combined_html = f"""
        <div style="display: flex; flex-direction: column; gap: 20px; width: 100%;">
            <div style="width: 100%;">
                {html1}
            </div>
            <div style="width: 100%;">
                {html2}
            </div>
        </div>
        """
        return combined_html
