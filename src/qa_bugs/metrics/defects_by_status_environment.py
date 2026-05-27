from __future__ import annotations

import pandas as pd
import plotly.express as px

from qa_bugs.metrics.base import Metric, MetricResult
from qa_bugs.metrics.defects_by_env_priority import DefectsByEnvPriority
from qa_bugs.metrics.status_by_severity import StatusBySeverity


class DefectsByStatusEnvironment(Metric):
    id = "defects_by_status_environment"
    display_name = "Defects by Status & Environment"
    requires = {"status", "environment"}

    def compute(self, df: pd.DataFrame, params: dict, profile=None) -> MetricResult:
        missing = [column for column in ("status", "environment") if column not in df.columns]
        if missing:
            return MetricResult(
                self.id,
                tables={
                    "status_environment": pd.DataFrame(columns=["environment", "status", "count"]),
                    "environment_counts": pd.DataFrame(columns=["environment", "count"]),
                },
                summary=f"Missing required fields: {', '.join(missing)}",
                skip_report=True,
            )

        d = df.copy()
        d["status"] = d["status"].astype("string").fillna("Unknown").str.strip()
        d.loc[d["status"].eq(""), "status"] = "Unknown"
        d["environment"] = d["environment"].apply(DefectsByEnvPriority._split_environment_value)
        d = d.explode("environment")
        d["environment"] = d["environment"].astype("string").str.strip()

        tbl = (
            d.groupby(["environment", "status"], dropna=False)
            .size()
            .reset_index(name="count")
        )

        environment_counts = (
            tbl.groupby("environment", dropna=False)["count"]
            .sum()
            .reset_index()
            .sort_values(["count", "environment"], ascending=[False, True])
        )
        environment_order = environment_counts["environment"].tolist()
        status_order = self._status_order(tbl["status"].astype(str).unique().tolist(), profile=profile)

        tbl["environment"] = pd.Categorical(tbl["environment"], categories=environment_order, ordered=True)
        tbl["status"] = pd.Categorical(tbl["status"], categories=status_order, ordered=True)
        tbl = tbl.sort_values(["environment", "status"])

        return MetricResult(
            self.id,
            tables={
                "status_environment": tbl,
                "environment_counts": environment_counts,
                "status_order": pd.DataFrame({"status": status_order}),
            },
            summary=f"Defects grouped by status and environment. Total: {int(tbl['count'].sum())}",
        )

    def build_figure(self, result: MetricResult) -> str:
        tbl = result.tables.get("status_environment")
        if tbl is None or tbl.empty:
            return ""

        environment_counts = result.tables.get("environment_counts")
        if environment_counts is not None and not environment_counts.empty:
            environment_order = environment_counts["environment"].astype(str).tolist()
        else:
            environment_order = tbl["environment"].astype(str).drop_duplicates().tolist()

        status_order_tbl = result.tables.get("status_order")
        if status_order_tbl is not None and not status_order_tbl.empty:
            status_order = status_order_tbl["status"].astype(str).tolist()
        else:
            status_order = tbl["status"].astype(str).drop_duplicates().tolist()

        plot_tbl = tbl.copy()
        plot_tbl["environment"] = plot_tbl["environment"].astype(str)
        plot_tbl["status"] = plot_tbl["status"].astype(str)
        status_colors = self._status_color_map(status_order)

        fig = px.bar(
            plot_tbl,
            x="environment",
            y="count",
            color="status",
            barmode="stack",
            title="Defects by Status and Environment",
            category_orders={"environment": environment_order, "status": status_order},
            color_discrete_map=status_colors,
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

    @staticmethod
    def _status_order(statuses: list[str], profile=None) -> list[str]:
        if profile and profile.status_profile:
            profile_order = (
                list(profile.status_profile.open_statuses)
                + list(profile.status_profile.closed_statuses)
                + list(profile.status_profile.rejected_statuses)
            )
            ordered = [status for status in profile_order if status in statuses]
            ordered.extend(sorted(status for status in statuses if status not in ordered))
            return ordered
        return sorted(statuses)

    @staticmethod
    def _status_color_map(statuses: list[str]) -> dict[str, str]:
        fallback_palette = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
            "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
            "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ab",
        ]
        default_colors = StatusBySeverity._build_default_colors()
        normalized_defaults = {
            status.casefold(): color
            for status, color in default_colors.items()
        }
        semantic_colors = {
            "assigned": "#6b7280",
            "reopen": "#d62728",
            "reopened": "#d62728",
            "open": "#ff7f0e",
            "blocked": "#f1c40f",
            "in development": "#1f77b4",
            "in uat": "#9467bd",
            "ready for production": "#dc7633",
            "ready for uat": "#8e44ad",
            "ready for qa": "#5dade2",
            "in qa": "#17becf",
            "development complete": "#16a085",
            "enhancement": "#bcbd22",
            "closed": "#2ca02c",
            "done": "#2ca02c",
            "rejected": "#7f8c8d",
            "cancelled": "#95a5a6",
            "canceled": "#95a5a6",
            "unknown": "#bdc3c7",
        }

        color_map = {}
        fallback_idx = 0
        for status in statuses:
            normalized = status.casefold().strip()
            if normalized in semantic_colors:
                color_map[status] = semantic_colors[normalized]
            elif normalized in normalized_defaults:
                color_map[status] = normalized_defaults[normalized]
            else:
                color_map[status] = fallback_palette[fallback_idx % len(fallback_palette)]
                fallback_idx += 1
        return color_map
