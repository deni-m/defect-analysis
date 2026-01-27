from typing import Any, Dict
import pandas as pd
import plotly.express as px
from qa_bugs.metrics.base import Metric, MetricResult

class DefectsByEnvPriority(Metric):
    id = "defects_by_env_priority"
    display_name = "Defects by Environment & Priority"

    def compute(self, df: pd.DataFrame, params: dict) -> MetricResult:
        # Validate required columns
        if "environment" not in df.columns or "priority" not in df.columns:
            missing = []
            if "environment" not in df.columns:
                missing.append("environment")
            if "priority" not in df.columns:
                missing.append("priority")
            return MetricResult(
                self.id,
                tables={"env_priority": pd.DataFrame(columns=["environment", "priority", "count"])},
                summary=f"Missing required fields: {', '.join(missing)}"
            )
        
        # Handle multiple environments per defect (comma-separated)
        df = df.copy()
        df["environment"] = df["environment"].astype(str).str.split(",")
        df = df.explode("environment")
        df["environment"] = df["environment"].str.strip().str.upper()
        
        tbl = (
            df.groupby(["environment", "priority"])
            .size()
            .reset_index(name="count")
        )
        
        # Order environments by total count (descending) - data-driven approach
        # No config-based env_order needed - we show only what exists in the data
        total_counts = tbl.groupby("environment", dropna=False)["count"].sum().reset_index()
        # Sort by descending count, then alphabetically for stability
        env_order_by_count = total_counts.sort_values(
            ["count", "environment"], 
            ascending=[False, True]
        )["environment"].tolist()
        
        # Apply categorical ordering
        tbl["environment"] = pd.Categorical(
            tbl["environment"], 
            categories=env_order_by_count, 
            ordered=True
        )
        tbl = tbl.sort_values("environment")
        
        summary = f"Defects grouped by environment and priority. Total: {tbl['count'].sum()}"
        
        # Build a debug table of unique environments (post-normalization) for troubleshooting ordering
        env_counts = (
            df.groupby("environment").size().reset_index(name="raw_count").sort_values("raw_count", ascending=False)
        )
        
        tables = {"env_priority": tbl, "env_counts": env_counts}
        
        # Store discovered environments for other metrics to use
        tables["discovered_environments"] = pd.DataFrame({
            "environment": env_order_by_count,
            "count": [total_counts[total_counts["environment"] == e]["count"].values[0] for e in env_order_by_count]
        })
        
        return MetricResult(
            metric_id=self.id,
            tables=tables,
            summary=summary,
        )

    def build_figure(self, result: MetricResult) -> str:
        tbl = result.tables.get("env_priority")
        if tbl is None or tbl.empty:
            return ""
        
        # Get environment order from the discovered environments table
        discovered_tbl = result.tables.get("discovered_environments")
        category_order = None
        if discovered_tbl is not None and not discovered_tbl.empty:
            category_order = discovered_tbl["environment"].tolist()
        
        # Ensure sort matches final category order if categorical exists
        if category_order is not None:
            tbl["environment"] = pd.Categorical(tbl["environment"], categories=category_order, ordered=True)
            tbl = tbl.sort_values("environment")
        
        # Priority color scheme (urgent to low urgency)
        priority_colors = {
            "Critical": "#c0392b",    # Dark red
            "Blocker": "#c0392b",     # Dark red
            "High": "#e74c3c",        # Red
            "Medium": "#f39c12",      # Orange
            "Low": "#3498db",         # Blue
            "Minor": "#3498db",       # Blue
            "Trivial": "#95a5a6",     # Gray
            "TBD": "#7f8c8d",         # Dark gray
            "Undefined": "#bdc3c7",   # Light gray
        }

        fig = px.bar(
            tbl,
            x="environment",
            y="count",
            color="priority",
            barmode="stack",
            title="Defects by Environment (stacked by Priority)",
            category_orders={"environment": category_order} if category_order is not None else None,
            color_discrete_map=priority_colors,
        )
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=50), height=350)
        return fig.to_html(include_plotlyjs=False, full_html=False)
