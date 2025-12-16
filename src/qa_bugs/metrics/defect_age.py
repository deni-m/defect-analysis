import pandas as pd
from .base import Metric, MetricResult, _df_to_records_json_safe

class DefectAge(Metric):
    id = "defect_age"
    display_name = "Defect Age Distribution"

    def compute(self, df: pd.DataFrame, cfg: dict) -> MetricResult:
        """Compute aggregated age statistics.

        Previous implementation returned a raw per-defect table ("defect_age"). To
        reduce LLM token usage we now emit only aggregated tables:
        - stats: overall distribution KPIs (count, avg_age, p50, p90, avg_age_closed)
        - age_by_priority: per-priority distribution (count, avg_age, p50, p90, max_age)
        - oldest_samples: top 5 oldest defects (key, priority, age_days) for context
        Raw rows are intentionally omitted.
        """
        d = df.copy()
        # Normalize timestamps: read as tz-aware (UTC) then drop tz -> naive UTC
        d["created_at"] = pd.to_datetime(d["created_at"], errors="coerce", utc=True).dt.tz_convert(None)
        d["resolved_at"] = pd.to_datetime(d["resolved_at"], errors="coerce", utc=True).dt.tz_convert(None)

        now = pd.Timestamp.utcnow().tz_localize(None)
        end = d["resolved_at"].fillna(now)
        d["age_days"] = (end - d["created_at"]).dt.days

        age_series = d["age_days"].dropna()
        has_age = age_series.notna().any()
        closed_mask = d["resolved_at"].notna()
        closed_age_series = d.loc[closed_mask, "age_days"].dropna()
        # Core KPI stats (all-time, not truncated)
        stats = {
            "count": int(d.shape[0]),
            "avg_age": float(age_series.mean()) if has_age else 0.0,
            "p50": float(age_series.median()) if has_age else 0.0,
            "p90": float(age_series.quantile(0.9)) if has_age else 0.0,
            "avg_age_closed": float(closed_age_series.mean()) if not closed_age_series.empty else None,
            # Explicit open / closed counts so UIs can compute backlog KPIs
            "open_count": int((d["resolved_at"].isna()).sum()),
            "closed_count": int((d["resolved_at"].notna()).sum()),
        }

        # Per-priority aggregation
        if "priority" in d.columns:
            by_prio = (
                d.groupby("priority")["age_days"]
                .agg(
                    count="count",
                    avg_age="mean",
                    p50="median",
                    p90=lambda s: s.quantile(0.9),
                    max_age="max",
                )
                .reset_index()
            )
            # Round numeric columns for readability
            num_cols = [c for c in by_prio.columns if c not in ["priority"]]
            by_prio[num_cols] = by_prio[num_cols].apply(lambda col: col.round(1))
        else:
            by_prio = pd.DataFrame(columns=["priority", "count", "avg_age", "p50", "p90", "max_age"])

        # Build age bucket distribution summary
        buckets = [
            ("0-30", (d["age_days"] <= 30)),
            ("31-90", (d["age_days"] > 30) & (d["age_days"] <= 90)),
            ("91-180", (d["age_days"] > 90) & (d["age_days"] <= 180)),
            (">180", (d["age_days"] > 180)),
        ]
        parts_bucket = []
        total_non_na = max(int(d["age_days"].notna().sum()), 1)
        for label, mask in buckets:
            pct = 100.0 * mask.sum() / total_non_na
            parts_bucket.append(f"{label}d={pct:.0f}%")
        age_distribution_summary = ", ".join(parts_bucket)

        # Build summary string
        summary_parts = [
            f"avg={stats['avg_age']:.1f}d",
            f"p50={stats['p50']:.0f}d",
            f"p90={stats['p90']:.0f}d",
            f"n={stats['count']}",
        ]
        if stats.get("avg_age_closed") is not None:
            summary_parts.append(f"avg_closed={stats['avg_age_closed']:.1f}d")
        summary = ", ".join(summary_parts)

        # SLA targets from cfg (expect mapping priority -> days)
        sla_targets = cfg.get("sla_targets")  # optional
        extra = {
            "data_date": pd.Timestamp.utcnow().date().isoformat(),
            "project": cfg.get("project") or cfg.get("__full_config__", {}).get("project"),
            "open_closed_ratio": f"open={stats['open_count']}, closed={stats['closed_count']}",
            "age_distribution_summary": age_distribution_summary,
            "sla_targets": sla_targets,
        }

        return DefectAgeResult(
            self.id,
            tables={
                "stats": pd.DataFrame([stats]),  # retained for report builder internal use
                "age_by_priority": by_prio,
                "defect_age_dist": d[["age_days"]].head(500),  # internal for histogram figure
                "defect_age": d[["resolved_at", "age_days"]].head(500),  # minimal table for report builder closed age calc
            },
            summary=summary,
            extra=extra,
        )

    def build_figure(self, result: MetricResult) -> str | None:
        import plotly.express as px
        # Prefer distribution table (histogram)
        dist_tbl = result.tables.get("defect_age_dist")
        if (dist_tbl is None or dist_tbl.empty) and "defect_age" in result.tables:
            dist_tbl = result.tables.get("defect_age")
        if dist_tbl is not None and not dist_tbl.empty and "age_days" in dist_tbl.columns:
            fig = px.histogram(
                dist_tbl,
                x="age_days",
                nbins=20,
                title="Defect Age Distribution (days)",
                color_discrete_sequence=["#3498db"]  # Nice blue instead of black
            )
            return fig.to_html(include_plotlyjs=False, full_html=False)
        # Fallback: use age_by_priority (bar of avg_age) but keep title consistent
        by_prio = result.tables.get("age_by_priority")
        if by_prio is not None and not by_prio.empty and {"priority", "avg_age"}.issubset(by_prio.columns):
            fig = px.bar(
                by_prio,
                x="priority",
                y="avg_age",
                title="Defect Age Distribution (days)",
                color_discrete_sequence=["#3498db"]  # Nice blue
            )
            return fig.to_html(include_plotlyjs=False, full_html=False)
        return None


class DefectAgeResult(MetricResult):
    """Custom MetricResult for defect age with optimized LLM payload.

    Internal tables may include 'stats' and 'age_by_priority'. The payload
    reduces noise and adds synthetic fields like open_closed_ratio, age_distribution_summary.
    Fields expected in payload dict:
      - data_date
      - project
      - sla_targets (optional mapping)
      - open_closed_ratio (string)
      - age_distribution_summary (string)
      - trend_summary (optional string)
    """
    def __init__(self, metric_id: str, tables: dict, summary: str, extra: dict):
        super().__init__(metric_id, tables=tables, summary=summary)
        self.extra = extra

    def payload(self) -> dict:
        out = {
            "metric_id": self.metric_id,
            "summary": self.summary,
        }
        for k in ["data_date", "project", "sla_targets", "open_closed_ratio", "age_distribution_summary", "trend_summary"]:
            v = self.extra.get(k)
            if v:
                out[k] = v
        # No tables included in LLM payload; summary stats provided in extra fields
        out["tables"] = {}
        return out

