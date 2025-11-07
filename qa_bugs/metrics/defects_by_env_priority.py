from typing import Any, Dict
import pandas as pd
import plotly.express as px
from qa_bugs.metrics.base import Metric, MetricResult

class DefectsByEnvPriority(Metric):
    id = "defects_by_env_priority"
    display_name = "Defects by Environment & Priority"

    def compute(self, df: pd.DataFrame, params: dict) -> MetricResult:
        # Handle multiple environments per defect (comma-separated)
        df = df.copy()
        df["environment"] = df["environment"].astype(str).str.split(",")
        df = df.explode("environment")
        df["environment"] = df["environment"].str.strip().str.upper()
        # Get environment order from config if present
        env_order = params.get("env_order")
        if env_order:
            # Normalize both data and config to uppercase for case-insensitive comparison
            env_order_upper = [e.upper() for e in env_order]
            df["environment"] = df["environment"].str.upper()
        else:
            env_order_upper = None
        tbl = (
            df.groupby(["environment", "priority"])
            .size()
            .reset_index(name="count")
        )
        # Determine final ordering: unknown envs (not in config) first by descending total count, then configured order
        final_order = None
        if env_order_upper is not None:
            total_counts = tbl.groupby("environment", dropna=False)["count"].sum().reset_index()
            known_set = set(env_order_upper)
            unknown_rows = total_counts[~total_counts["environment"].isin(known_set)]
            # Sort unknowns by descending count then alphabetically for stability
            unknown_sorted = unknown_rows.sort_values(["count", "environment"], ascending=[False, True])["environment"].tolist()
            final_order = unknown_sorted + env_order_upper
            # Apply categorical with combined order so labels are preserved (no NaN collapse)
            tbl["environment"] = pd.Categorical(tbl["environment"], categories=final_order, ordered=True)
            tbl = tbl.sort_values("environment")
        summary = f"Defects grouped by environment and priority. Total: {tbl['count'].sum()}"
        # Build a debug table of unique environments (post-normalization) for troubleshooting ordering
        env_counts = (
            df.groupby("environment").size().reset_index(name="raw_count").sort_values("raw_count", ascending=False)
        )
        tables = {"env_priority": tbl, "env_counts": env_counts}
        if env_order_upper is not None:
            # Store as DataFrame (Series caused .to_dict(orient="records") TypeError in payload serialization)
            tables["env_order_upper"] = pd.DataFrame({
                "environment": env_order_upper,
                "order_index": list(range(len(env_order_upper)))
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
        env_order_upper = None
        env_order_tbl = result.tables.get("env_order_upper")
        if env_order_tbl is not None and not env_order_tbl.empty and "environment" in env_order_tbl.columns:
            env_order_upper = env_order_tbl["environment"].tolist()
        # Build final order again (unknown first) for plotting if we have configured order
        category_order = None
        if env_order_upper is not None:
            total_counts = tbl.groupby("environment", dropna=False)["count"].sum().reset_index()
            known_set = set(env_order_upper)
            unknown_sorted = (
                total_counts[~total_counts["environment"].isin(known_set)]
                .sort_values(["count", "environment"], ascending=[False, True])["environment"].tolist()
            )
            category_order = unknown_sorted + env_order_upper
        # Ensure sort matches final category order if categorical exists
        if category_order is not None:
            tbl["environment"] = pd.Categorical(tbl["environment"], categories=category_order, ordered=True)
            tbl = tbl.sort_values("environment")
        fig = px.bar(
            tbl,
            x="environment",
            y="count",
            color="priority",
            barmode="stack",
            title="Defects by Environment (stacked by Priority)",
            category_orders={"environment": category_order} if category_order is not None else None,
        )
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=350)
        return fig.to_html(include_plotlyjs=False, full_html=False)
