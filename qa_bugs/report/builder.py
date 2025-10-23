from __future__ import annotations

from typing import Dict, Iterable, Optional

import plotly.express as px
import plotly.graph_objects as go
from jinja2 import Template

# Single minimal inline template (fast, no external dependency at runtime)
HTML_TEMPLATE = """<!doctype html><html><head><meta charset='utf-8'/><title>{{ title }}</title>
<script src='https://cdn.plot.ly/plotly-2.30.0.min.js'></script>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:24px;background:#f5f7fa}
h1,h2,h3{margin:0.4em 0}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:18px;margin:20px 0;box-shadow:0 2px 4px rgba(0,0,0,.04)}
.kpi{display:flex;gap:16px;flex-wrap:wrap}
.kpi .item{flex:1 1 200px;background:#f1f5f9;border-radius:10px;padding:12px}
.kpi .item b{display:block;font-size:0.8rem;text-transform:uppercase;letter-spacing:.5px;color:#334155;margin-bottom:4px}
ul{padding-left:18px}
.insight{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px;margin-top:16px}
.insight h3{font-size:0.95rem;margin:0 0 8px 0;color:#0f172a}
.insight ul{margin:0;padding-left:20px}
.insight li{font-size:0.85rem;line-height:1.15rem;color:#334155;margin-bottom:4px}
.insight p{font-size:0.85rem;line-height:1.25rem;margin:0 0 6px 0;color:#334155}
</style></head><body>
<h1>{{ title }}</h1>
{% if overall_html %}<div class='card'><h2>Overall Summary (LLM)</h2>{{ overall_html | safe }}</div>{% endif %}
{% if summary_kpi_html %}{{ summary_kpi_html | safe }}{% endif %}
{% for mid in metric_order %}
    {% if figures.get(mid) %}
    <div class='card'><h2>{{ mid }}</h2>{{ figures.get(mid) | safe }}{% if insights_html.get(mid) %}{{ insights_html.get(mid) | safe }}{% endif %}</div>
    {% endif %}
{% endfor %}
</body></html>"""


def _first_present(d: dict, keys: Iterable[str], default=None):
    """Return the first non-null/ non-empty value for any of the candidate keys.

    Treat 0 as a valid value (so we check `is not None` instead of truthiness),
    and skip empty strings.
    """
    for k in keys:
        if k in d:
            v = d[k]
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            return v
    return default


class ReportBuilder:
    """Build an interactive HTML report for metric results.

    Responsibilities:
    - Convert tabular metric outputs into simple Plotly figures.
    - Extract KPI style numbers (currently leakage rate) using a tolerant alias set
      so historical / future naming tweaks don't break the report.
    - Combine optional LLM-generated insights.
    """

    # Column name aliases for leakage KPI extraction
    _LEAKAGE_ALIASES = {
        "rate_percent": ["rate_percent", "leakage_percent", "leakage"],
        "leaked": ["leaked", "leaked_count"],
        "caught": ["caught", "not_leaked_count"],
        "total": ["total", "total_considered"],
    }

    def build(
        self,
        results: Dict,
        insights: Optional[Dict] = None,
        overall: Optional[str] = None,
        title: str = "QA Bug Analytics Report",
        metric_order: Optional[Iterable[str]] = None,
    ) -> str:
        figures: Dict[str, str] = {}
        # Per-metric additional fragments (e.g., KPI grids) decoupled from metric build_figure
        extra_fragments: Dict[str, str] = {}
        def _format_insight(text: str, heading: str = "Insight") -> str:
            """Convert raw LLM text into a styled HTML block.

            Rules:
            - Lines starting with '###' or '##' are treated as subheadings (ignored, we use heading param).
            - Lines starting with '-', '*', or numbered '1.' become bullet items.
            - Other non-empty lines become paragraph elements.
            - Empty lines create paragraph breaks.
            """
            if not text or not text.strip():
                return ""
            lines = [l.rstrip() for l in text.splitlines()]
            bullets: list[str] = []  # unordered
            ordered: list[str] = []  # numbered
            paras: list[str] = []
            current_para: list[str] = []
            for ln in lines:
                stripped = ln.strip()
                if not stripped:
                    if current_para:
                        paras.append(" ".join(current_para))
                        current_para = []
                    continue
                if stripped.startswith(("-", "*")):
                    if current_para:
                        paras.append(" ".join(current_para))
                        current_para = []
                    bullets.append(stripped.lstrip("-* "))
                    continue
                # numbered list like '1. text'
                if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == '.':
                    if current_para:
                        paras.append(" ".join(current_para))
                        current_para = []
                    ordered.append(stripped[2:].strip())
                    continue
                # Convert markdown headings (###, ##, #) into bullet items instead of headers
                if stripped.startswith("###") or stripped.startswith("##") or stripped.startswith("#"):
                    heading_text = stripped.lstrip("#").strip()
                    if heading_text:
                        if current_para:
                            paras.append(" ".join(current_para))
                            current_para = []
                        bullets.append(heading_text)
                    continue
                # Lines that are only bold (e.g., **Issue** or **High Risk**) become bullets
                if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
                    bold_text = stripped.strip("*").strip()
                    if bold_text:
                        if current_para:
                            paras.append(" ".join(current_para))
                            current_para = []
                        bullets.append(bold_text)
                    continue
                current_para.append(stripped)
            if current_para:
                paras.append(" ".join(current_para))
            html_parts = ["<div class='insight'>", f"<h3>{heading}</h3>"]
            if paras:
                for p in paras:
                    html_parts.append(f"<p>{p}</p>")
            if bullets:
                html_parts.append("<ul>")
                for b in bullets:
                    html_parts.append(f"<li>{b}</li>")
                html_parts.append("</ul>")
            if ordered:
                html_parts.append("<ol>")
                for o in ordered:
                    html_parts.append(f"<li>{o}</li>")
                html_parts.append("</ol>")
            html_parts.append("</div>")
            return "".join(html_parts)

        # Prepare containers for high-level KPI extraction
        summary_kpi_html = ""
        total_defects = None
        avg_age_all = None
        p90_age = None  # will be collected but not displayed (user request to remove)
        avg_age_closed = None
        leakage_pct = None
        leaked_count = None
        closed_defects = None
        opened_defects = None

        # First pass: extract KPIs without producing figures (to allow independent ordering later)
        for mid, res in results.items():
            if mid == "defect_age":
                stats_tbl = res.tables.get("stats")
                if stats_tbl is not None and not stats_tbl.empty:
                    stats_row = stats_tbl.iloc[0].to_dict()
                    total_defects = int(stats_row.get("count", 0))
                    avg_age_all = float(stats_row.get("avg_age", 0.0))
                    p90_age = float(stats_row.get("p90", 0.0))
                tbl = res.tables.get("defect_age")
                if tbl is not None and not tbl.empty and {"resolved_at", "age_days"}.issubset(tbl.columns):
                    closed_mask = tbl["resolved_at"].notna()
                    if closed_mask.any():
                        try:
                            avg_age_closed = float(tbl.loc[closed_mask, "age_days"].mean())
                        except Exception:
                            avg_age_closed = None
            elif mid == "cumulative_open_closed":
                summary_tbl = res.tables.get("summary")
                if summary_tbl is not None and not summary_tbl.empty:
                    row = summary_tbl.iloc[0].to_dict()
                    opened_defects = int(row.get("opened_cum", 0))
                    closed_defects = int(row.get("closed_cum", 0))
                    if total_defects is None:
                        total_defects = opened_defects
            elif mid == "leakage_rate":
                leak_res = res
                overall_tbl = leak_res.tables.get("leakage_overall")
                legacy_tbl = leak_res.tables.get("leakage_overall_kpis")
                row = None
                if overall_tbl is not None and not overall_tbl.empty:
                    row = overall_tbl.iloc[0].to_dict()
                elif legacy_tbl is not None and not legacy_tbl.empty:
                    row = legacy_tbl.iloc[0].to_dict()
                if row:
                    rate = _first_present(row, self._LEAKAGE_ALIASES["rate_percent"], 0)
                    leaked_v = _first_present(row, self._LEAKAGE_ALIASES["leaked"], 0)
                    caught_v = _first_present(row, self._LEAKAGE_ALIASES["caught"], 0)
                    total_v = _first_present(row, self._LEAKAGE_ALIASES["total"], 0)
                    leakage_pct = float(rate) if isinstance(rate, (int, float)) else None
                    leaked_count = int(leaked_v) if isinstance(leaked_v, (int, float)) else None
                    if total_defects is None:
                        total_defects = int(total_v) if isinstance(total_v, (int, float)) else None
                    # Build metric-specific KPI fragment (generic rendering, no HTML in metric class)
                    def _pct_disp(v):
                        try:
                            s = f"{float(v):.1f}".rstrip("0").rstrip(".")
                            return s
                        except Exception:
                            return str(v)
                    frag = (
                        "<div class='kpi'>"
                        f"<div class='item'><b>Leakage</b><div>{_pct_disp(rate)}%</div></div>"
                        f"<div class='item'><b>Leaked</b><div>{leaked_v}</div></div>"
                        f"<div class='item'><b>Caught</b><div>{caught_v}</div></div>"
                        f"<div class='item'><b>Total</b><div>{total_v}</div></div>"
                        "</div>"
                    )
                    extra_fragments[mid] = frag

        # Second pass: build figures in desired order
        figure_order = list(metric_order) if metric_order else list(results.keys())
        from qa_bugs.metrics import METRICS as _METRICS_REGISTRY  # reused to instantiate for build_figure
        # Instantiate metric objects (lightweight) for figure building
        metric_objs = {mid: _METRICS_REGISTRY[mid]() for mid in figure_order if mid in _METRICS_REGISTRY}
        for mid in figure_order:
            res = results.get(mid)
            if res is None:
                continue
            metric_obj = metric_objs.get(mid)
            if metric_obj is None:
                continue
            fig_html = metric_obj.build_figure(res)
            if fig_html:
                # Prepend any extra fragments (e.g., KPI grid) for this metric
                prefix = extra_fragments.get(mid, "")
                figures[mid] = prefix + fig_html

        # Compose summary KPI row HTML if we have at least one primary metric
        if total_defects is not None:
            def fmt_days(v: Optional[float]) -> str:
                if v is None:
                    return "-"
                try:
                    return f"{v:.1f}d".replace(".0d", "d")
                except Exception:
                    return "-"
            open_pct = None
            if closed_defects is not None and total_defects:
                open_count = total_defects - closed_defects
                if total_defects > 0:
                    open_pct = round(open_count / total_defects * 100.0, 1)
            def pct_fmt(v: Optional[float]) -> str:
                if v is None:
                    return "-"
                try:
                    s = f"{v:.1f}".rstrip("0").rstrip(".")
                    return s
                except Exception:
                    return str(v)
            open_block = "-"
            if open_pct is not None and closed_defects is not None:
                open_count = total_defects - closed_defects
                open_block = f"{pct_fmt(open_pct)}% ({open_count} bugs)"
            leakage_block = "-"
            if leakage_pct is not None:
                leak_pct_disp = pct_fmt(leakage_pct)
                if leaked_count is not None:
                    leakage_block = f"{leak_pct_disp}% ({leaked_count} leaked)"
                else:
                    leakage_block = f"{leak_pct_disp}%"
            summary_kpi_html = (
                "<div class='card'><h2>Summary KPIs</h2><div class='kpi'>"
                f"<div class='item'><b>Total Defects</b><div>{total_defects}</div></div>"
                f"<div class='item'><b>Open</b><div>{open_block}</div></div>"
                f"<div class='item'><b>Leakage</b><div>{leakage_block}</div></div>"
                f"<div class='item'><b>Avg Age</b><div>{fmt_days(avg_age_all)}</div></div>"
                f"<div class='item'><b>Avg Closed Age</b><div>{fmt_days(avg_age_closed)}</div></div>"
                "</div></div>"
            )

        # Pre-format insights
        insights_html: Dict[str, str] = {}
        if insights:
            for mid, txt in insights.items():
                fmt = _format_insight(txt, heading="Insight")
                if fmt:
                    insights_html[mid] = fmt
        overall_html = _format_insight(overall, heading="Overall Summary") if overall else ""

        # Reorder figures according to explicit metric_order if provided
        if metric_order:
            ordered_figures = {}
            for mid in metric_order:
                if mid in figures:
                    ordered_figures[mid] = figures[mid]
            # Include any remaining figures not in metric_order (edge-case) preserving their insertion order
            for mid in figures:
                if mid not in ordered_figures:
                    ordered_figures[mid] = figures[mid]
            figures_to_render = ordered_figures
        else:
            figures_to_render = figures

        tpl = Template(HTML_TEMPLATE)
        # Determine final ordered list for template iteration
        final_order = list(metric_order) if metric_order else list(figures_to_render.keys())
        return tpl.render(
            title=title,
            results=results,
            insights_html=insights_html,
            overall_html=overall_html,
            figures=figures_to_render,
            summary_kpi_html=summary_kpi_html,
            metric_order=final_order,
        )

