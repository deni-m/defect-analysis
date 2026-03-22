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

    def compute(self, df: pd.DataFrame, ctx: dict, profile=None) -> MetricResult:
        """Compute leakage rate supporting both legacy full-config ctx and new merged per-metric params.

        New style (after CLI change): ctx is a dict merged from common + metric-specific params and contains:
            exclude_statuses, intended_env (optional), leak_envs (optional)
            plus __full_config__ pointing to the original root config (ignored here).

        Legacy style (pre-change): ctx was the full root config containing nested metrics.params.*.
        We detect that and extract similarly so the metric remains backward compatible.
        """
        if ctx is None:
            ctx = {}

        # Detect legacy structure
        if "metrics" in ctx and "params" in ctx.get("metrics", {}):
            metrics_params = ctx["metrics"].get("params", {})
            merged = {**metrics_params.get("common", {}), **metrics_params.get(self.id, {})}
            merged["__full_config__"] = ctx
            ctx = merged

        # At this point ctx is the merged params dict
        exclude_statuses = set(ctx.get("exclude_statuses", []))
        intended_envs = ctx.get("intended_env", [])
        leak_envs = ctx.get("leak_envs", [])

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

        if not isinstance(intended_envs, list):
            raise ValueError("leakage_rate: 'intended_env' must be a list, e.g. ['QA'].")
        if not isinstance(leak_envs, list):
            raise ValueError("leakage_rate: 'leak_envs' must be a list, e.g. ['UAT','PROD'].")

        intended_envs = [str(x).upper() for x in intended_envs if x is not None]
        leak_envs = [str(x).upper() for x in leak_envs if x is not None]

        # Validate that configured environments exist in the data
        import logging
        logger = logging.getLogger(__name__)
        
        # Collect all unique environments from data
        token_counter = Counter()
        for tokens in env_lists:
            token_counter.update(tokens)
        actual_envs = set(token_counter.keys())
        
        # Warn about missing intended_envs
        if intended_envs:
            missing_intended = set(intended_envs) - actual_envs
            if missing_intended:
                logger.warning(
                    f"Leakage Rate: intended_env contains environments not found in data: {missing_intended}. "
                    f"Available environments: {sorted(actual_envs)}"
                )
        
        # Warn about missing leak_envs
        if leak_envs:
            missing_leak = set(leak_envs) - actual_envs
            if missing_leak:
                logger.warning(
                    f"Leakage Rate: leak_envs contains environments not found in data: {missing_leak}. "
                    f"Available environments: {sorted(actual_envs)}"
                )

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
        env_counts_preview = "; ".join(f"{k}:{v}" for k, v in token_counter.most_common(10)) or "(no env values)"
        
        # Enhanced debug info
        logger.info(f"Leakage Rate Debug - Config: intended_env={intended_envs}, leak_envs={leak_envs}")
        logger.info(f"Leakage Rate Debug - Environment distribution: {dict(token_counter)}")
        logger.info(f"Leakage Rate Debug - Total: {total}, Leaked: {leaked}, Caught: {caught}, Rate: {leakage_pct}%")
        
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

                # Apply priority ordering from profile if available
                if profile is not None and profile.priority_profile and profile.priority_profile.severity_order:
                    order = profile.priority_profile.severity_order
                    by_priority["priority"] = pd.Categorical(
                        by_priority["priority"], categories=order, ordered=True
                    )
                    by_priority = by_priority.sort_values("priority")

                tables["leakage_by_priority"] = by_priority

                fig = px.bar(
                    by_priority,
                    x="priority",
                    y="leakage_percent",
                    title="Leakage % by Priority",
                    color_discrete_sequence=["#5470C6"],  # Blue color
                )
                # Show percentage and absolute number and total atop each bar
                fig.update_traces(
                    text=[
                        f"{int(row['leakage_percent'])}% ({int(row['leaked'])} out of {int(row['total'])})"
                        for _, row in by_priority.iterrows()
                    ],
                    textposition="outside",
                )
                # Dynamic upper y bound ensures threshold (5%) is visible with headroom
                y_max = max(5, by_priority["leakage_percent"].max() * 1.15)
                fig.update_layout(
                    margin=dict(t=50, b=50),
                    yaxis=dict(title="leakage_percent", range=[0, y_max]),
                    height=350
                )
                # Add thin horizontal threshold line at 5% (risk threshold)
                threshold = 5.0
                if y_max >= threshold:
                    fig.add_shape(
                        type="line",
                        x0=-0.5,
                        x1=len(by_priority["priority"]) - 0.5,
                        y0=threshold,
                        y1=threshold,
                        line=dict(color="red", width=1, dash="solid"),
                    )
                    fig.add_annotation(
                        x=len(by_priority["priority"]) - 0.5,
                        y=threshold,
                        text="5% threshold",
                        showarrow=False,
                        xanchor="right",
                        yanchor="bottom",
                        font=dict(color="red", size=10),
                        bgcolor="rgba(255,255,255,0.6)",
                        bordercolor="red",
                        borderwidth=0,
                    )
                charts["leakage_by_priority"] = fig

        return MetricResult(
            self.id,
            tables=tables,
            charts=charts,
            summary=f"Leakage={leakage_pct}% (leaked {leaked}/{total})",
        )

    def build_figure(self, result: MetricResult) -> str | None:
        """Return KPI panel + bar chart HTML; data table handled by ReportBuilder."""
        # Build KPI panel from overall table
        overall = result.tables.get("leakage_overall")
        kpi_html = ""
        if overall is not None and not overall.empty:
            row = overall.iloc[0]
            rate = row.get("rate_percent", row.get("leakage_percent", 0))
            leaked = int(row.get("leaked", row.get("leaked_count", 0)))
            caught = int(row.get("caught", row.get("not_leaked_count", 0)))
            total = int(row.get("total", row.get("total_considered", 0)))

            def _pct_disp(v):
                try:
                    s = f"{float(v):.1f}".rstrip("0").rstrip(".")
                    return s
                except Exception:
                    return str(v)

            kpi_html = (
                "<div class='kpi'>"
                f"<div class='item'><b>LEAKAGE</b><div>{_pct_disp(rate)}%</div></div>"
                f"<div class='item'><b>LEAKED</b><div>{leaked}</div></div>"
                f"<div class='item'><b>CAUGHT</b><div>{caught}</div></div>"
                f"<div class='item'><b>TOTAL</b><div>{total}</div></div>"
                "</div>"
            )

        # Build chart
        chart_obj = result.charts.get("leakage_by_priority")
        chart_html = ""
        if chart_obj is None:
            by_priority = result.tables.get("leakage_by_priority")
            if by_priority is None or by_priority.empty:
                return kpi_html if kpi_html else None
            import plotly.express as px
            y_col = None
            for cand in ("leakage_percent", "rate_percent"):
                if cand in by_priority.columns:
                    y_col = cand
                    break
            if y_col is None:
                return kpi_html if kpi_html else None
            plot_df = by_priority.copy()
            if "priority" in plot_df.columns:
                plot_df["priority"] = plot_df["priority"].astype(object).fillna("TBD")
            fig = px.bar(
                plot_df,
                x="priority",
                y=y_col,
                title="Leakage % by Priority",
                color_discrete_sequence=["#5470C6"]  # Blue color
            )
            fig.update_layout(margin=dict(t=50, b=50), height=350)
            chart_html = fig.to_html(include_plotlyjs=False, full_html=False, config={'displayModeBar': False})
        else:
            try:
                chart_html = chart_obj.to_html(include_plotlyjs=False, full_html=False, config={'displayModeBar': False})
            except Exception:
                chart_html = ""

        # Combine KPI panel and chart
        return kpi_html + chart_html if (kpi_html or chart_html) else None
