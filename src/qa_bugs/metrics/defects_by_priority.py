import pandas as pd
import plotly.express as px

from qa_bugs.metrics.base import Metric, MetricResult
from qa_bugs.metrics.defects_by_env_priority import DefectsByEnvPriority


class DefectsByPriority(Metric):
    id = "defects_by_priority"
    display_name = "Defects by Priority"

    def compute(self, df: pd.DataFrame, params: dict, profile=None) -> MetricResult:
        if "priority" not in df.columns:
            return MetricResult(
                self.id,
                tables={"priority_counts": pd.DataFrame(columns=["priority", "count", "percent"])},
                summary="Missing required field: priority",
                quality_notes=["Metric could not be calculated: required field 'priority' is missing."],
            )

        d = df.copy()
        d["priority"] = d["priority"].astype("string").fillna("TBD").str.strip()
        d.loc[d["priority"].eq(""), "priority"] = "TBD"

        total = int(len(d))
        tbl = (
            d.groupby("priority", dropna=False)
            .size()
            .reset_index(name="count")
        )
        tbl["percent"] = tbl["count"].apply(lambda count: round(count / total * 100.0, 2) if total else 0.0)

        if profile is not None and profile.priority_profile and profile.priority_profile.severity_order:
            severity_order = [p for p in profile.priority_profile.severity_order if p in set(tbl["priority"])]
            remaining = [p for p in tbl["priority"].tolist() if p not in severity_order]
            priority_order = severity_order + sorted(remaining)
            tbl["priority"] = pd.Categorical(tbl["priority"], categories=priority_order, ordered=True)
            tbl = tbl.sort_values("priority")
        else:
            tbl = tbl.sort_values(["count", "priority"], ascending=[False, True])

        summary = f"Defects grouped by priority. Total: {total}"
        return MetricResult(
            metric_id=self.id,
            tables={"priority_counts": tbl},
            summary=summary,
        )

    def build_figure(self, result: MetricResult) -> str:
        tbl = result.tables.get("priority_counts")
        if tbl is None or tbl.empty:
            return ""

        plot_tbl = tbl.copy()
        plot_tbl["priority"] = plot_tbl["priority"].astype(str)
        plot_tbl["label"] = plot_tbl.apply(
            lambda row: f"{int(row['count'])} ({float(row['percent']):.2f}%)",
            axis=1,
        )
        priority_colors = DefectsByEnvPriority._build_priority_color_map(plot_tbl["priority"].unique())

        fig = px.bar(
            plot_tbl,
            x="priority",
            y="count",
            color="priority",
            text="label",
            title="Defects by Priority",
            color_discrete_map=priority_colors,
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(
            margin=dict(l=72, r=72, t=72, b=72),
            height=460,
            showlegend=False,
            yaxis_title_standoff=16,
            xaxis_title_standoff=12,
            uniformtext=dict(mode="show"),
        )
        fig.update_yaxes(automargin=True, ticklabelposition="outside")
        fig.update_xaxes(automargin=True)
        return fig.to_html(include_plotlyjs=False, full_html=False)
