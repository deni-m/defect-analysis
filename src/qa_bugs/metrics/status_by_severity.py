from __future__ import annotations

from typing import Optional
import pandas as pd
import plotly.express as px

from .base import Metric, MetricResult


class StatusBySeverity(Metric):
    """Distribution of issue statuses across severities (priority used as severity proxy).

    Tables:
    - status_by_severity_raw: each row per defect with normalized priority & status.
    - status_by_severity_summary: aggregated counts and percentages per (priority, status).
    - status_by_severity_pivot: wide pivot table (priority rows x status columns, counts).

    Chart:
    - Stacked bar chart of statuses per priority ordered by total count descending.
    
    If DataProfile is provided, uses AI-classified open/closed statuses for color coding.
    """

    id = "status_by_severity"
    display_name = "Status by Severity"
    requires = {"status", "priority"}

    def compute(self, df: pd.DataFrame, ctx: dict, profile: Optional["DataProfile"] = None) -> MetricResult:
        if df.empty:
            return MetricResult(self.id, summary="No data")

        d = df.copy()
        # Normalize columns if present
        if "priority" in d.columns:
            d["priority"] = d["priority"].astype("string").fillna("TBD")
        else:
            d["priority"] = "TBD"
        if "status" in d.columns:
            d["status"] = d["status"].astype("string").fillna("Unknown")
        else:
            d["status"] = "Unknown"

        raw = d[["priority", "status"]].copy()

        # Summary counts
        summary = (
            raw.groupby(["priority", "status"], dropna=False)
            .size()
            .reset_index(name="count")
        )
        total_by_priority = summary.groupby("priority")['count'].transform('sum')
        grand_total = float(summary['count'].sum()) or 1.0
        summary['percent_priority'] = summary['count'] / total_by_priority * 100.0
        summary['percent_overall'] = summary['count'] / grand_total * 100.0

        # Pivot for wide view
        pivot = summary.pivot(index="priority", columns="status", values="count").fillna(0).astype(int)
        totals = pivot.sum(axis=1)
        pivot = pivot.loc[totals.sort_values(ascending=False).index]

        # Build stacked bar chart data frame: use profile severity_order when available, else sort by total
        existing_priorities = pivot.index.tolist()
        if profile is not None and profile.priority_profile and profile.priority_profile.severity_order:
            severity_order = profile.priority_profile.severity_order
            priority_order = [p for p in severity_order if p in existing_priorities]
            # Append any priorities not in the profile order at the end
            priority_order += [p for p in existing_priorities if p not in priority_order]
        else:
            priority_order = existing_priorities
        # To keep consistent color ordering, maintain alphabetical status ordering
        status_order = sorted(pivot.columns.tolist())
        long_df = summary.copy()
        long_df['priority'] = pd.Categorical(long_df['priority'], categories=priority_order, ordered=True)
        long_df['status'] = pd.Categorical(long_df['status'], categories=status_order, ordered=True)

        # Add text labels: percent + count for each status/priority
        long_df['label'] = long_df.apply(
            lambda r: f"{r['percent_priority']:.0f}% ({int(r['count'])})", axis=1
        )

        # Define custom colors for statuses
        # If profile is provided, use semantic color mapping (green=closed, blue=open, gray=rejected)
        # Otherwise use hardcoded palette
        if profile and profile.status_profile:
            status_colors = self._build_profile_colors(
                profile.status_profile, 
                long_df['status'].unique().tolist()
            )
        else:
            status_colors = self._build_default_colors()
        
        fig = px.bar(
            long_df,
            x="priority",
            y="percent_priority",
            color="status",
            title="Status Distribution by Severity (Priority) — Relative %",
            text="label",
            color_discrete_map=status_colors,
        )
        # Legend positioning: place horizontally below the chart, centered.
        fig.update_layout(
            barmode="stack",
            legend_title_text="Status",
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,  # push legend below plot area
                xanchor="center",
                x=0.5,
            ),
            margin=dict(b=100),  # extra bottom margin so legend not clipped
            yaxis=dict(title="Percent per Priority", range=[0, 100])
        )

        # Build simplified aggregation for LLM context (only severity, status, count)
        llm_summary = summary[['priority', 'status', 'count']].copy()
        llm_summary.rename(columns={'priority': 'severity'}, inplace=True)

        tables = {
            "status_by_severity_raw": raw,
            "status_by_severity_summary": summary,
            "status_by_severity_pivot": pivot,
            "status_by_severity_llm": llm_summary,  # Simplified for LLM
        }
        charts = {"status_by_severity": fig}

        top_priority = priority_order[0] if priority_order else None
        top_total = int(pivot.sum(axis=1).iloc[0]) if not pivot.empty else 0
        summary_text = (
            f"Relative stacked status distribution across priorities. Top priority '{top_priority}' has {top_total} issues." if top_priority else "No priorities"
        )
        return MetricResult(
            self.id,
            tables=tables,
            charts=charts,
            summary=summary_text,
            llm_tables=["status_by_severity_llm"]  # Only send simplified table to LLM
        )

    def build_figure(self, result: MetricResult) -> str | None:
        chart_obj = result.charts.get("status_by_severity")
        if chart_obj is None:
            return None
        try:
            return chart_obj.to_html(include_plotlyjs=False, full_html=False)
        except Exception:
            return None
    
    @staticmethod
    def _build_profile_colors(status_profile: "StatusProfile", all_statuses: list) -> dict:
        """Build semantic color map based on AI classification."""
        colors = {}
        
        # Closed statuses: green shades
        green_shades = ["#2ca02c", "#27ae60", "#1e8449", "#16a085"]
        for i, status in enumerate(status_profile.closed_statuses):
            colors[status] = green_shades[i % len(green_shades)]
        
        # Open statuses: blue shades  
        blue_shades = ["#3498db", "#2980b9", "#5dade2", "#8e44ad", "#e67e22", "#ff7f0e", "#f39c12"]
        for i, status in enumerate(status_profile.open_statuses):
            colors[status] = blue_shades[i % len(blue_shades)]
        
        # Rejected statuses: gray shades
        gray_shades = ["#95a5a6", "#7f8c8d", "#bdc3c7"]
        for i, status in enumerate(status_profile.rejected_statuses):
            colors[status] = gray_shades[i % len(gray_shades)]
        
        # Unknown statuses: default gray
        for status in all_statuses:
            if status not in colors:
                colors[status] = "#bdc3c7"
        
        return colors
    
    @staticmethod
    def _build_default_colors() -> dict:
        """Build hardcoded color palette (fallback when no profile)."""
        return {
            # Completed states (green shades)
            "Done": "#2ca02c",
            "Resolved": "#27ae60",
            "Closed": "#1e8449",

            # In progress states (blue/purple shades)
            "In Progress": "#3498db",
            "Implementing": "#2980b9",
            "IN QA": "#8e44ad",
            "Code Review": "#9b59b6",
            "Ready for QA": "#5dade2",

            # Waiting states (orange shades)
            "To Do": "#e67e22",
            "Open": "#ff7f0e",
            "Funnel": "#f39c12",
            "Analysis": "#d68910",
            "Ready for Production": "#dc7633",
            "Ready for Acceptance": "#ca6f1e",

            # On hold/blocked states (amber/yellow)
            "Blocked / On Hold": "#f1c40f",
            "On Hold": "#f4d03f",

            # Cancelled/rejected states (gray)
            "Cancelled": "#95a5a6",
            "Rejected": "#7f8c8d",

            # Other
            "Accepted": "#16a085",
            "Unknown": "#bdc3c7",
        }
