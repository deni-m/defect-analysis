from __future__ import annotations

from collections import Counter

import pandas as pd
import plotly.express as px

from .base import Metric, MetricResult


class LeakageRate(Metric):
    """
    Defect leakage metric:
    - Ignores defects in statuses listed in global exclusion:
      ctx["metrics"]["params"]["common"]["exclude_statuses"] (exact match).
    - Requires:
        ctx["metrics"]["params"]["leakage_rate"]["intended_env"] -> list[str]
        ctx["metrics"]["params"]["leakage_rate"]["leak_envs"]    -> list[str] (may be empty)
    - 'leaked' logic:
        * if leak_envs not empty: leaked = any environment token ∈ leak_envs
        * else if intended_env not empty: leaked = has any environment token and some token ∉ intended_env
        * else (both empty): leaked = has any non-empty environment token
    """

    id = "leakage_rate"
    display_name = "Leakage Rate"
    requires = {"status", "environment"}

    def compute(self, df: pd.DataFrame, ctx: dict) -> MetricResult:
        # 0) Metric parameters branch
        params_root = ctx.get("metrics", {})
        metrics_params = params_root.get("params", {})

        params = metrics_params.get(self.id, {})
        common = metrics_params.get("common", {})
        exclude_statuses = set(common.get("exclude_statuses", []))

        d = df.copy()

        # Initial row count (for debug)
        n0 = int(len(d))

        # 1) Filter out globally excluded statuses
        if "status" in d.columns and exclude_statuses:
            d = d[~d["status"].isin(exclude_statuses)]

        n_after_status = int(len(d))

        # 2) Normalize environment(s); support comma separated multiple values
        raw_env = d.get("environment")
        if raw_env is not None:
            raw_env = raw_env.astype("string").fillna("")
        else:
            raw_env = pd.Series([""] * len(d), index=d.index, dtype="string")

        env_lists = raw_env.str.split(",").apply(
            lambda parts: [p.strip().upper() for p in parts if p and p.strip()]
        )
        env_joined = env_lists.apply(lambda lst: ",".join(lst))
        d["environment_normalized"] = env_joined

        # 3) Parameters (must be lists)
        intended_envs = params.get("intended_env", [])
        leak_envs = params.get("leak_envs", [])

        if not isinstance(intended_envs, list):
            raise ValueError("leakage_rate: 'intended_env' must be a list, e.g. ['QA'].")
        if not isinstance(leak_envs, list):
            raise ValueError("leakage_rate: 'leak_envs' must be a list, e.g. ['UAT','PROD'].")

        intended_envs = [str(x).upper() for x in intended_envs if x is not None]
        leak_envs = [str(x).upper() for x in leak_envs if x is not None]

        # 4) Leakage mask (multi-env aware)
        if leak_envs:
            leaked_mask = env_lists.apply(lambda tokens: any(t in leak_envs for t in tokens))
            rule_used = f"leak_envs(any)={leak_envs}"
        elif intended_envs:
            leaked_mask = env_lists.apply(lambda tokens: len(tokens) > 0 and any(t not in intended_envs for t in tokens))
            rule_used = f"intended_env(any outside)={intended_envs}"
        else:
            leaked_mask = env_lists.apply(lambda tokens: len(tokens) > 0)
            rule_used = "fallback: any token present"

        d["leaked"] = leaked_mask

        # 5) KPI aggregation
        total = int(len(d))
        leaked = int(d["leaked"].sum()) if total else 0
        caught = int((~d["leaked"]).sum()) if total else 0
        leakage_pct = round((leaked / total * 100.0), 2) if total else 0.0

        # Overall table (duplicate columns kept for backward compatibility)
        overall = pd.DataFrame(
            {
                "metric": ["leakage_rate"],
                "rate_percent": [leakage_pct],
                "leaked": [leaked],
                "caught": [caught],
                "total": [total],
                "leakage_percent": [leakage_pct],
                "leaked_count": [leaked],
                "not_leaked_count": [caught],
                "total_considered": [total],
            }
        )

        # 6) Debug table (environment token distribution)
        token_counter = Counter()
        for tokens in env_lists:
            token_counter.update(tokens)
        env_counts_preview = "; ".join(f"{k}:{v}" for k, v in token_counter.most_common(5)) or ""
        debug = pd.DataFrame(
            {
                "phase": ["initial", "after_status_filter", "final"],
                "rows": [n0, n_after_status, int(len(d))],
                "rule_used": [rule_used, rule_used, rule_used],
                "env_preview": [env_counts_preview, env_counts_preview, env_counts_preview],
            }
        )

        tables = {
            "leakage_overall": overall,
            "leakage_debug": debug,
        }
        charts = {}

        # 7) Priority breakdown (optional)
        if total > 0 and "priority" in d.columns:
            by_priority = (
                d.groupby("priority", dropna=False)
                .agg(total=("environment", "size"), leaked=("leaked", "sum"))
                .reset_index()
            )
            if not by_priority.empty:
                by_priority["leakage_percent"] = by_priority.apply(
                    lambda r: round((r["leaked"] / r["total"] * 100.0), 2) if r["total"] > 0 else 0.0,
                    axis=1,
                )
                tables["leakage_by_priority"] = by_priority

                fig = px.bar(
                    by_priority,
                    x="priority",
                    y="leakage_percent",
                    title="Leakage % by Priority",
                )
                # Show percentage and absolute number and total atop each bar
                fig.update_traces(
                    text=[
                        f"{int(row['leakage_percent'])}% ({int(row['leaked'])} out of {int(row['total'])})"
                        for _, row in by_priority.iterrows()
                    ],
                    textposition="outside",
                )
                fig.update_layout(
                    margin=dict(t=50, b=20),
                    yaxis=dict(title="leakage_percent", range=[0, max(5, by_priority["leakage_percent"].max() * 1.15)])
                )
                charts["leakage_by_priority"] = fig

        return MetricResult(
            self.id,
            tables=tables,
            charts=charts,
            summary=f"Leakage={leakage_pct}% (leaked {leaked}/{total})",
        )

    def build_figure(self, result: MetricResult) -> str | None:
        """Return bar chart HTML; data table handled by ReportBuilder."""
        chart_obj = result.charts.get("leakage_by_priority")
        if chart_obj is None:
            by_priority = result.tables.get("leakage_by_priority")
            if by_priority is None or by_priority.empty:
                return None
            import plotly.express as px
            y_col = None
            for cand in ("leakage_percent", "rate_percent"):
                if cand in by_priority.columns:
                    y_col = cand
                    break
            if y_col is None:
                return None
            plot_df = by_priority.copy()
            if "priority" in plot_df.columns:
                plot_df["priority"] = plot_df["priority"].astype(object).fillna("TBD")
            fig = px.bar(plot_df, x="priority", y=y_col, title="Leakage % by Priority")
            return fig.to_html(include_plotlyjs=False, full_html=False)
        try:
            return chart_obj.to_html(include_plotlyjs=False, full_html=False)
        except Exception:
            return None
