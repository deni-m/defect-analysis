from typing import Any, Dict
import re
import pandas as pd
import plotly.express as px
from qa_bugs.metrics.base import Metric, MetricResult
from qa_bugs.metrics.priority_ordering import normalize_priority, ordered_priorities

class DefectsByEnvPriority(Metric):
    id = "defects_by_env_priority"
    display_name = "Defects by Environment & Priority"
    UNSPECIFIED_ENVIRONMENT = "Unspecified"

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
        
        # Capture fill rate BEFORE exploding (original row count is meaningful)
        orig_total = len(df)
        orig_filled = int(
            df["environment"]
            .apply(lambda value: not self._is_missing_environment_value(value))
            .sum()
        )

        # Handle multiple environments per defect (comma-separated)
        df = df.copy()
        df["environment"] = df["environment"].apply(self._split_environment_value)
        df = df.explode("environment")
        df["environment"] = df["environment"].astype("string").str.strip()
        df["priority"] = df["priority"].map(normalize_priority)
        
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
        
        unspecified_count = orig_total - orig_filled
        environment_coverage = pd.DataFrame([{
            "total_defects": orig_total,
            "tagged_defects": orig_filled,
            "unspecified_defects": unspecified_count,
            "tagged_percent": round(orig_filled / orig_total * 100.0, 2) if orig_total else 0.0,
            "unspecified_percent": round(unspecified_count / orig_total * 100.0, 2) if orig_total else 0.0,
        }])

        tables = {
            "env_priority": tbl,
            "env_counts": env_counts,
            "environment_coverage": environment_coverage,
        }
        
        # Store discovered environments for other metrics to use
        tables["discovered_environments"] = pd.DataFrame({
            "environment": env_order_by_count,
            "count": [total_counts[total_counts["environment"] == e]["count"].values[0] for e in env_order_by_count]
        })
        
        # Check env fill rate — if too sparse, results are unreliable
        env_quality_notes = []
        if orig_total > 0 and orig_filled / orig_total < 0.05:
            env_quality_notes = [
                f"Low data quality: only {orig_filled}/{orig_total} rows "
                f"({orig_filled/orig_total*100:.1f}%) have environment data. "
                "Results are unreliable and should not be used to draw conclusions."
            ]

        return MetricResult(
            metric_id=self.id,
            tables=tables,
            summary=summary,
            quality_notes=env_quality_notes,
        )

    @classmethod
    def _is_missing_environment_value(cls, value: Any) -> bool:
        if pd.isna(value):
            return True
        normalized = str(value).strip().lower()
        return normalized in {"", "nan", "none", "<na>", "null"}

    @classmethod
    def _split_environment_value(cls, value: Any) -> list[str]:
        if cls._is_missing_environment_value(value):
            return [cls.UNSPECIFIED_ENVIRONMENT]

        tokens = []
        for token in str(value).split(","):
            cleaned = token.strip()
            if cls._is_missing_environment_value(cleaned):
                continue
            tokens.append(cleaned.upper())

        return tokens or [cls.UNSPECIFIED_ENVIRONMENT]

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
        
        priority_order = ordered_priorities(tbl["priority"].dropna().astype(str).unique())
        priority_colors = self._build_priority_color_map(priority_order)

        fig = px.bar(
            tbl,
            x="environment",
            y="count",
            color="priority",
            barmode="stack",
            title="Defects by Environment (stacked by Priority)",
            category_orders={
                **({"environment": category_order} if category_order is not None else {}),
                "priority": priority_order,
            },
            color_discrete_map=priority_colors,
        )
        fig.update_layout(
            margin=dict(l=90, r=24, t=48, b=64),
            height=420,
            yaxis_title_standoff=16,
            xaxis_title_standoff=12,
        )
        fig.update_yaxes(automargin=True, ticklabelposition="outside")
        fig.update_xaxes(automargin=True)
        return fig.to_html(include_plotlyjs=False, full_html=False)

    @classmethod
    def _build_priority_color_map(cls, priorities) -> dict[str, str]:
        fallback_palette = [
            "#5470C6", "#91CC75", "#FAC858", "#73C0DE", "#3BA272",
            "#FC8452", "#9A60B4", "#EA7CCC", "#2F5597", "#70AD47",
        ]
        color_map = {}
        fallback_idx = 0

        for priority in sorted(str(p) for p in priorities):
            semantic_color = cls._semantic_priority_color(priority)
            if semantic_color:
                color_map[priority] = semantic_color
            else:
                color_map[priority] = fallback_palette[fallback_idx % len(fallback_palette)]
                fallback_idx += 1

        return color_map

    @staticmethod
    def _semantic_priority_color(priority: str) -> str | None:
        tokens = {
            token
            for token in re.split(r"[^a-z0-9]+", priority.lower())
            if token
        }
        normalized = " ".join(tokens)

        if "showstopper" in tokens or "blocker" in tokens:
            return "#7f1d1d"
        if "critical" in tokens or "p0" in tokens:
            return "#c0392b"
        if "major" in tokens or "high" in tokens or "p1" in tokens:
            return "#e67e22"
        if "average" in tokens or "medium" in tokens or "normal" in tokens or "p2" in tokens:
            return "#f39c12"
        if "minor" in tokens or "low" in tokens or "p3" in tokens:
            return "#3498db"
        if "trivial" in tokens or "lowest" in tokens or "p4" in tokens:
            return "#95a5a6"
        if normalized in {"tbd", "undefined", "unknown"}:
            return "#7f8c8d"
        return None
