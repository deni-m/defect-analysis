import re

import pandas as pd
import plotly.express as px

from qa_bugs.metrics.base import Metric, MetricResult


class RootCauseDistribution(Metric):
    id = "root_cause_distribution"
    display_name = "Root Cause Distribution"
    UNSPECIFIED = "Unspecified"
    MAX_DISPLAY_LABEL_CHARS = 70

    def compute(self, df: pd.DataFrame, params: dict, profile=None) -> MetricResult:
        if "root_cause" not in df.columns:
            return MetricResult(
                self.id,
                tables={"root_cause_counts": pd.DataFrame(columns=["root_cause", "count", "percent"])},
                summary="Missing required field: root_cause",
                skip_report=True,
            )

        total = int(len(df))
        cleaned = df["root_cause"].map(self._clean_root_cause)
        specified = cleaned[cleaned != self.UNSPECIFIED]
        specified_count = int(len(specified))

        if specified_count == 0:
            return MetricResult(
                self.id,
                tables={"root_cause_counts": pd.DataFrame(columns=["root_cause", "count", "percent"])},
                summary="No root cause values found",
                skip_report=True,
            )

        top_n = int(params.get("top_n", 10))
        counts = specified.value_counts().reset_index()
        counts.columns = ["root_cause", "count"]

        if self._looks_like_free_text(specified, counts):
            return MetricResult(
                self.id,
                tables={
                    "root_cause_counts": pd.DataFrame(columns=[
                        "root_cause",
                        "count",
                        "percent",
                        "percent_of_specified",
                        "percent_of_total",
                    ]),
                    "root_cause_coverage": pd.DataFrame([{
                        "total_defects": total,
                        "specified_defects": specified_count,
                        "unspecified_defects": total - specified_count,
                        "specified_percent": round(specified_count / total * 100.0, 2) if total else 0.0,
                        "unspecified_percent": round((total - specified_count) / total * 100.0, 2) if total else 0.0,
                        "unique_root_causes": int(counts.shape[0]),
                        "shown_groups": 0,
                    }]),
                },
                summary="Root cause values look like free-text descriptions, not reusable groups",
                skip_report=True,
            )

        top = counts.head(top_n).copy()
        other_count = int(counts.iloc[top_n:]["count"].sum()) if len(counts) > top_n else 0
        if other_count:
            top = pd.concat([
                top,
                pd.DataFrame([{"root_cause": "Other", "count": other_count}]),
            ], ignore_index=True)

        top["percent_of_specified"] = top["count"].apply(
            lambda count: round(count / specified_count * 100.0, 2) if specified_count else 0.0
        )
        top["percent_of_total"] = top["count"].apply(
            lambda count: round(count / total * 100.0, 2) if total else 0.0
        )
        # Backward-compatible alias used by existing prompts/tests: percent of specified root-cause values.
        top["percent"] = top["percent_of_specified"]

        coverage = pd.DataFrame([{
            "total_defects": total,
            "specified_defects": specified_count,
            "unspecified_defects": total - specified_count,
            "specified_percent": round(specified_count / total * 100.0, 2) if total else 0.0,
            "unspecified_percent": round((total - specified_count) / total * 100.0, 2) if total else 0.0,
            "unique_root_causes": int(counts.shape[0]),
            "shown_groups": int(top.shape[0]),
        }])

        return MetricResult(
            metric_id=self.id,
            tables={
                "root_cause_counts": top,
                "root_cause_coverage": coverage,
            },
            summary=f"Root cause distribution. Specified={specified_count}/{total}",
            llm_tables=["root_cause_counts", "root_cause_coverage"],
        )

    def build_figure(self, result: MetricResult) -> str:
        tbl = result.tables.get("root_cause_counts")
        if tbl is None or tbl.empty:
            return ""

        plot_tbl = tbl.copy()
        percent_col = "percent_of_specified" if "percent_of_specified" in plot_tbl.columns else "percent"
        plot_tbl["root_cause_display"] = plot_tbl["root_cause"].map(self._truncate_label)
        plot_tbl["label"] = plot_tbl.apply(
            lambda row: f"{int(row['count'])} ({float(row[percent_col]):.2f}%)",
            axis=1,
        )

        fig = px.bar(
            plot_tbl,
            x="count",
            y="root_cause_display",
            orientation="h",
            text="label",
            title="Top Root Cause Groups (% of specified root causes)",
            hover_data={
                "root_cause": True,
                "root_cause_display": False,
                "percent_of_specified": ":.2f" if "percent_of_specified" in plot_tbl.columns else False,
                "percent_of_total": ":.2f" if "percent_of_total" in plot_tbl.columns else False,
            },
        )
        fig.update_traces(
            marker_color="#3498db",
            textposition="outside",
            cliponaxis=False,
        )
        fig.update_layout(
            margin=dict(l=180, r=96, t=56, b=48),
            height=max(420, 70 + len(plot_tbl) * 36),
            showlegend=False,
            xaxis_title="count",
            yaxis_title="root cause",
        )
        fig.update_yaxes(autorange="reversed", automargin=True)
        fig.update_xaxes(automargin=True)
        return fig.to_html(include_plotlyjs=False, full_html=False)

    @classmethod
    def _clean_root_cause(cls, value) -> str:
        if pd.isna(value):
            return cls.UNSPECIFIED
        text = re.sub(r"\s+", " ", str(value).strip())
        if not text or text.lower() in {"nan", "none", "<na>", "null"}:
            return cls.UNSPECIFIED
        return text

    @classmethod
    def _truncate_label(cls, value: str) -> str:
        text = str(value)
        if len(text) <= cls.MAX_DISPLAY_LABEL_CHARS:
            return text
        return text[: cls.MAX_DISPLAY_LABEL_CHARS - 3].rstrip() + "..."

    @staticmethod
    def _looks_like_free_text(specified: pd.Series, counts: pd.DataFrame) -> bool:
        specified_count = int(len(specified))
        if specified_count < 10:
            return False

        unique_ratio = counts.shape[0] / specified_count
        avg_len = float(specified.astype(str).str.len().mean())
        long_value_ratio = float((specified.astype(str).str.len() > 120).mean())

        return unique_ratio >= 0.8 and (avg_len > 80 or long_value_ratio >= 0.25)
