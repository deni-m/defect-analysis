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
.kpi .item.risk-warn{background:#fff4e6;border:1px solid #ffb347}
.kpi .item.risk-high{background:#ffe5e5;border:1px solid #ff6b6b}
.kpi .item.risk-ok{background:#e6f9ed;border:1px solid #34c759}
.kpi .item b{display:block;font-size:0.8rem;text-transform:uppercase;letter-spacing:.5px;color:#334155;margin-bottom:4px}
ul{padding-left:18px}
.insight{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px;margin-top:16px}
.insight h3{font-size:0.95rem;margin:0 0 8px 0;color:#0f172a}
.insight ul{margin:0;padding-left:20px}
.insight li{font-size:0.85rem;line-height:1.15rem;color:#334155;margin-bottom:4px}
.insight p{font-size:0.85rem;line-height:1.25rem;margin:0 0 6px 0;color:#334155}
/* Chart layout helpers */
.chart-half-right{display:flex;}
.chart-half-right .inner{flex:0 0 50%;margin-left:auto;}
</style></head><body>
<h1>{{ title }}</h1>
{% if summary_kpi_html %}{{ summary_kpi_html | safe }}{% endif %}
{% if overall_html %}<div class='card'>{{ overall_html | safe }}</div>{% endif %}
{% for mid in metric_order %}
    {% if figures.get(mid) %}
    <div class='card'><h2>{{ display_names.get(mid, mid) }}</h2>{{ figures.get(mid) | safe }}{% if insights_html.get(mid) %}{{ insights_html.get(mid) | safe }}{% endif %}</div>
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
        header_prefix: Optional[str] = None,  # NEW: optional prefix for report header
    ) -> str:
        figures: Dict[str, str] = {}
        # Per-metric additional fragments (e.g., KPI grids) decoupled from metric build_figure
        extra_fragments: Dict[str, str] = {}
        def _format_insight(text: str, heading: str = "Insight") -> str:
            """Render LLM markdown preserving section grouping.

            Section model:
            - Each heading (#/##/###) starts a new section.
            - Paragraph lines accumulate under current section until blank or list item.
            - Bullets / ordered items belong to the section where they appear.
            - Bold-only lines (**text**) treated as bullet emphasis.
            - If no heading encountered before content, all goes into an implicit section.
            """
            if not text or not text.strip():
                return ""
            lines = [l.rstrip() for l in text.splitlines()]
            sections: list[dict] = []  # [{title:str|None, paras:[], bullets:[], ordered:[]}]
            current = {"title": None, "paras": [], "bullets": [], "ordered": []}
            def push_para():
                if para_buf:
                    current["paras"].append(" ".join(para_buf))
                    para_buf.clear()
            para_buf: list[str] = []
            for raw in lines:
                stripped = raw.strip()
                if not stripped:
                    push_para()
                    continue
                # Heading
                if stripped.startswith("###") or stripped.startswith("##") or stripped.startswith("#"):
                    push_para()
                    # Start new section
                    if current["title"] is not None or current["paras"] or current["bullets"] or current["ordered"]:
                        sections.append(current)
                        current = {"title": None, "paras": [], "bullets": [], "ordered": []}
                    current["title"] = stripped.lstrip("#").strip()
                    continue
                # Unordered bullet: keep inline markdown (don't strip leading '**')
                if stripped.startswith("-") or stripped.startswith("*"):
                    push_para()
                    # Remove only the first list marker and following space
                    bullet_body = stripped[1:].lstrip()  # safe because startswith '-' or '*'
                    # Filter out separator artifacts like '--', '---', '-- --'
                    if all(ch == '-' for ch in bullet_body) and len(bullet_body) <= 3:
                        continue
                    if bullet_body in {"--", "---"}:
                        continue
                    if bullet_body.replace("-", "").strip() == "":  # purely dashes/spaces
                        continue
                    current["bullets"].append(bullet_body)
                    continue
                # Ordered bullet pattern (1. ...) -> normalize to unordered bullet for consistent style
                if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == '.':
                    push_para()
                    item_text = stripped[2:].strip()
                    # Avoid capturing empty artifact items
                    if item_text and item_text not in {"--", "---"}:
                        current["bullets"].append(item_text)
                    continue
                # Bold-only line -> treat as bullet emphasis but preserve ** for inline processing
                if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
                    push_para()
                    current["bullets"].append(stripped)
                    continue
                # Default text -> paragraph buffer
                para_buf.append(stripped)
            push_para()
            # Append last section if it has any content
            if current["title"] is not None or current["paras"] or current["bullets"] or current["ordered"]:
                sections.append(current)
            def _apply_inline_markdown(s: str) -> str:
                # Replace **bold** with <strong>bold</strong>; non-greedy.
                import re
                out = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{m.group(1).strip()}</strong>", s)
                # Remove unmatched orphaned '**' (e.g., produced by truncation) -> replace with ''
                out = re.sub(r"\*{2,}", "", out)  # any remaining sequences of ** become empty
                # Collapse multiple spaces
                out = re.sub(r"\s{2,}", " ", out).strip()
                return out

            html_parts = ["<div class='insight'>"]
            if heading:
                html_parts.append(f"<h3>{heading}</h3>")
            for sec in sections:
                if sec["title"]:
                    html_parts.append(f"<h4>{_apply_inline_markdown(sec['title'])}</h4>")
                for p in sec["paras"]:
                    html_parts.append(f"<p>{_apply_inline_markdown(p)}</p>")
                if sec["bullets"]:
                    html_parts.append("<ul>")
                    for b in sec["bullets"]:
                        html_parts.append(f"<li>{_apply_inline_markdown(b)}</li>")
                    html_parts.append("</ul>")
                # Ordered list removed (normalized to bullets); ignore sec["ordered"]
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
        rejection_pct = None
        rejected_count = None

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
            elif mid == "rejection_rate":
                # Avoid boolean ambiguity with DataFrame by selecting explicitly
                rej_tbl = res.tables.get("rejection_summary")
                if rej_tbl is None or rej_tbl.empty:
                    alt_tbl = res.tables.get("summary")
                    if alt_tbl is not None and not alt_tbl.empty:
                        rej_tbl = alt_tbl
                if rej_tbl is not None and not rej_tbl.empty:
                    rej_row = rej_tbl.iloc[0].to_dict()
                    rejection_pct = float(rej_row.get("rejection_percent", 0)) if isinstance(rej_row.get("rejection_percent"), (int, float)) else None
                    rejected_val = rej_row.get("rejected", 0)
                    total_val = rej_row.get("total", None)
                    rejected_count = int(rejected_val) if isinstance(rejected_val, (int, float)) else None
                    if total_defects is None and isinstance(total_val, (int, float)):
                        total_defects = int(total_val)
                    # Build metric-specific fragment (simple KPI trio)
                    def _pct_disp2(v):
                        try:
                            s = f"{float(v):.1f}".rstrip("0").rstrip(".")
                            return s
                        except Exception:
                            return str(v)
                    frag = (
                        "<div class='kpi'>"
                        f"<div class='item'><b>Rejection Rate</b><div>{_pct_disp2(rej_row.get('rejection_percent', 0))}%</div></div>"
                        f"<div class='item'><b>Rejected</b><div>{rej_row.get('rejected', 0)}</div></div>"
                        f"<div class='item'><b>Total</b><div>{rej_row.get('total', 0)}</div></div>"
                        "</div>"
                    )
                    extra_fragments[mid] = frag

        # Second pass: build figures in desired order
        figure_order = list(metric_order) if metric_order else list(results.keys())
        from qa_bugs.metrics import METRICS as _METRICS_REGISTRY  # reused to instantiate for build_figure
        # Instantiate metric objects (lightweight) for figure building
        metric_objs = {mid: _METRICS_REGISTRY[mid]() for mid in figure_order if mid in _METRICS_REGISTRY}
        display_names = {mid: getattr(metric_objs[mid], "display_name", mid) for mid in metric_objs}
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
                # Apply layout wrapper for leakage_rate (right aligned half width) centrally
                if mid == "leakage_rate":
                    fig_html = f'<div class=""><div class="inner">{fig_html}</div></div>'
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
            rejection_block = "-"
            if rejection_pct is not None:
                rej_pct_disp = pct_fmt(rejection_pct)
                if rejected_count is not None:
                    rejection_block = f"{rej_pct_disp}% ({rejected_count} rejected)"
                else:
                    rejection_block = f"{rej_pct_disp}%"
            # Determine risk classes based on thresholds
            leakage_class = ""
            if leakage_pct is not None:
                if leakage_pct > 10:
                    leakage_class = " risk-high"
                elif leakage_pct > 5:
                    leakage_class = " risk-warn"
                else:
                    leakage_class = " risk-ok"
            rejection_class = ""
            if rejection_pct is not None:
                if rejection_pct > 20:
                    rejection_class = " risk-high"
                elif rejection_pct > 10:
                    rejection_class = " risk-warn"
                else:
                    rejection_class = " risk-ok"
            summary_kpi_html = (
                "<div class='card'><h2>Summary KPIs</h2><div class='kpi'>"
                f"<div class='item'><b>Total Defects</b><div>{total_defects}</div></div>"
                f"<div class='item'><b>Open</b><div>{open_block}</div></div>"
                f"<div class='item{leakage_class}'><b>Leakage</b><div>{leakage_block}</div></div>"
                f"<div class='item{rejection_class}'><b>Rejection</b><div>{rejection_block}</div></div>"
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
        overall_html = _format_insight(overall, heading=None) if overall else ""

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
        # Compose final title with optional prefix
        final_title = f"{header_prefix} {title}" if header_prefix else title
        return tpl.render(
            title=final_title,
            results=results,
            insights_html=insights_html,
            overall_html=overall_html,
            figures=figures_to_render,
            summary_kpi_html=summary_kpi_html,
            metric_order=final_order,
            display_names=display_names,
        )

