from __future__ import annotations

import pandas as pd
import plotly.express as px

from .base import Metric, MetricResult


class LeakageRate(Metric):
    """
    Defect leakage metric:
    - Ігнорує баги у статусах зі списку глобального виключення:
      ctx["metrics"]["params"]["common"]["exclude_statuses"] (точні значення).
    - Вимагає:
        ctx["metrics"]["params"]["leakage_rate"]["intended_env"] -> list[str]
        ctx["metrics"]["params"]["leak_envs"]    -> list[str] (може бути порожнім)
    - Логіка 'leaked':
        * якщо leak_envs не порожній: leaked = environment ∈ leak_envs
        * інакше: leaked = environment != "" та environment ∉ intended_env
        * якщо обидва порожні: leaked = environment != ""
    """

    id = "leakage_rate"
    requires = {"status", "environment"}

    def compute(self, df: pd.DataFrame, ctx: dict) -> MetricResult:
        # 0) Параметри метрики з гілки metrics.params у контексті
        params_root = ctx.get("metrics", {})
        metrics_params = params_root.get("params", {})

        params = metrics_params.get(self.id, {})
        common = metrics_params.get("common", {})
        exclude_statuses = set(common.get("exclude_statuses", []))

        d = df.copy()

        # ---- DEBUG: початкові розміри
        n0 = int(len(d))

        # 1) Відсікаємо глобально виключені статуси
        if "status" in d.columns and exclude_statuses:
            d = d[~d["status"].isin(exclude_statuses)]

        n_after_status = int(len(d))

        # 2) Нормалізуємо environment до UPPER (порожні -> "")
        env = d.get("environment")
        if env is not None:
            env = env.astype("string").fillna("").str.upper()
        else:
            env = pd.Series([""] * len(d), index=d.index, dtype="string")

        # 3) Параметри метрики (суворо списки)
        intended_envs = params.get("intended_env", [])
        leak_envs = params.get("leak_envs", [])

        if not isinstance(intended_envs, list):
            raise ValueError("leakage_rate: 'intended_env' must be a list of environments, e.g. ['QA'].")
        if not isinstance(leak_envs, list):
            raise ValueError("leakage_rate: 'leak_envs' must be a list of environments, e.g. ['UAT','PROD'].")

        intended_envs = [str(x).upper() for x in intended_envs if x is not None]
        leak_envs = [str(x).upper() for x in leak_envs if x is not None]

        # 4) Маска leakage
        if leak_envs:
            leaked_mask = env.isin(leak_envs)
            rule_used = f"leak_envs={leak_envs}"
        elif intended_envs:
            leaked_mask = (env != "") & (~env.isin(intended_envs))
            rule_used = f"intended_env(exclude)={intended_envs}"
        else:
            leaked_mask = env != ""
            rule_used = "fallback: env != ''"

        d["leaked"] = leaked_mask

        # 5) KPI
        total = int(len(d))
        leaked = int(d["leaked"].sum()) if total else 0
        caught = int((~d["leaked"]).sum()) if total else 0  # раніше not_leaked
        leakage_pct = round((leaked / total * 100.0), 2) if total else 0.0

        # Узагальнена таблиця. Дублюємо значення у кількох назвах колонок для сумісності.
        # Builder очікує: rate_percent, leaked, caught, total
        # Історичні назви: leakage_percent, leaked_count, not_leaked_count, total_considered
        overall = pd.DataFrame(
            {
                "metric": ["leakage_rate"],
                # нові очікувані builder'ом
                "rate_percent": [leakage_pct],
                "leaked": [leaked],
                "caught": [caught],
                "total": [total],
                # збережені старі / альтернативні назви
                "leakage_percent": [leakage_pct],
                "leaked_count": [leaked],
                "not_leaked_count": [caught],
                "total_considered": [total],
            }
        )

        # 6) Debug-таблиця для діагностики
        env_counts = env.value_counts(dropna=False)
        debug = pd.DataFrame(
            {
                "phase": ["initial", "after_status_filter", "final"],
                "rows": [n0, n_after_status, total],
                "rule_used": [rule_used, rule_used, rule_used],
            }
        )
        dbg_env_preview = "; ".join([f"{k}:{int(v)}" for k, v in env_counts.head(5).items()])
        debug["env_preview"] = [dbg_env_preview, dbg_env_preview, dbg_env_preview]

        tables = {
            "leakage_overall": overall,
            "leakage_debug": debug,
        }
        charts = {}

        # 7) Breakdown за пріоритетами (тільки якщо є дані)
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
                charts["leakage_by_priority"] = fig

        return MetricResult(
            self.id,
            tables=tables,
            charts=charts,
            summary=f"Leakage={leakage_pct}% (leaked {leaked}/{total})",
        )

    def build_figure(self, result: MetricResult) -> str | None:
        """Return only the chart HTML for leakage breakdown.

        KPI (grid) rendering is now the responsibility of the ReportBuilder,
        so we keep this focused purely on visualization. This improves
        separation of concerns (metric = data; builder = presentation).
        """
        chart_obj = result.charts.get("leakage_by_priority")
        if chart_obj is None:
            # Fallback to building from table if chart wasn't pre-generated (edge-case)
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
        # Chart object already exists; serialize
        try:
            return chart_obj.to_html(include_plotlyjs=False, full_html=False)
        except Exception:
            return None
