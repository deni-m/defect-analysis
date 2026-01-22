"""HTML report generation for CLI."""
from __future__ import annotations

from typing import Dict, List, Optional, Iterable
from jinja2 import Template

from qa_bugs.services.models import AnalysisResult
from qa_bugs.metrics import METRICS

# Reuse the same HTML template from the original report builder
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
.chart-half-right{display:flex;}
.chart-half-right .inner{flex:0 0 50%;margin-left:auto;}
.profile-section{background:#f0f9ff;border:1px solid #bfdbfe;border-radius:10px;padding:12px;margin:10px 0;font-size:0.85rem}
.profile-section h4{margin:0 0 8px 0;color:#1e40af;font-size:0.9rem}
.profile-section .badge{display:inline-block;background:#dbeafe;color:#1e3a8a;padding:2px 8px;border-radius:4px;margin:2px;font-size:0.75rem}
.profile-section .confidence{color:#16a34a;font-weight:600}
</style></head><body>
<h1>{{ title }}</h1>
{% if data_profile_html %}{{ data_profile_html | safe }}{% endif %}
{% if summary_kpi_html %}{{ summary_kpi_html | safe }}{% endif %}
{% if overall_html %}<div class='card'>{{ overall_html | safe }}</div>{% endif %}
{% for mid in metric_order %}
    {% if figures.get(mid) %}
    <div class='card'><h2>{{ display_names.get(mid, mid) }}</h2>{{ figures.get(mid) | safe }}{% if insights_html.get(mid) %}{{ insights_html.get(mid) | safe }}{% endif %}</div>
    {% endif %}
{% endfor %}
</body></html>"""


def _first_present(d: dict, keys: Iterable[str], default=None):
    """Return the first non-null/non-empty value for any of the candidate keys."""
    for k in keys:
        if k in d:
            v = d[k]
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            return v
    return default


class HTMLReportGenerator:
    """
    Generates HTML reports from AnalysisResult.

    This is CLI-specific presentation logic - separated from core analysis.
    """

    # Column name aliases for leakage KPI extraction
    _LEAKAGE_ALIASES = {
        "rate_percent": ["rate_percent", "leakage_percent", "leakage"],
        "leaked": ["leaked", "leaked_count"],
        "caught": ["caught", "not_leaked_count"],
        "total": ["total", "total_considered"],
    }

    def generate(
        self,
        result: AnalysisResult,
        title: str = "QA Bug Analytics Report",
        header_prefix: Optional[str] = None,
        metric_order: Optional[List[str]] = None
    ) -> str:
        """
        Generate complete HTML report from analysis result.

        Args:
            result: AnalysisResult from AnalysisService
            title: Report title
            header_prefix: Optional prefix for title
            metric_order: Order of metrics in report

        Returns:
            Complete HTML string
        """
        # Use provided order or default to result order
        if metric_order is None:
            metric_order = result.metric_ids

        # Build figures and extract KPIs
        figures, extra_fragments, kpi_data = self._build_figures_and_kpis(
            result, metric_order
        )

        # Build summary KPI HTML
        summary_kpi_html = self._build_summary_kpis(kpi_data)
        
        # Build data profile HTML
        data_profile_html = self._build_data_profile(result.data_profile) if result.data_profile else ""

        # Format insights
        insights_html = self._format_insights(result.metric_insights)
        overall_html = self._format_insight(result.overall_summary, heading=None)

        # Get display names
        metric_objs = {mid: METRICS[mid]() for mid in metric_order if mid in METRICS}
        display_names = {mid: getattr(metric_objs[mid], "display_name", mid) for mid in metric_objs}

        # Compose final title
        final_title = f"{header_prefix} {title}" if header_prefix else title

        # Render template
        tpl = Template(HTML_TEMPLATE)
        return tpl.render(
            title=final_title,
            data_profile_html=data_profile_html,
            summary_kpi_html=summary_kpi_html,
            overall_html=overall_html,
            figures=figures,
            insights_html=insights_html,
            metric_order=metric_order,
            display_names=display_names
        )

    def _build_figures_and_kpis(self, result: AnalysisResult, metric_order: List[str]):
        """Build HTML figures and extract KPI data."""
        figures = {}
        extra_fragments = {}
        kpi_data = {
            "total_defects": None,
            "avg_age_all": None,
            "p90_age": None,
            "avg_age_closed": None,
            "leakage_pct": None,
            "leaked_count": None,
            "closed_defects": None,
            "opened_defects": None,
            "rejection_pct": None,
            "rejected_count": None
        }

        # First pass: extract KPIs
        for mid, res in result.metrics_results.items():
            if mid == "defect_age":
                stats_tbl = res.tables.get("stats")
                if stats_tbl is not None and not stats_tbl.empty:
                    stats_row = stats_tbl.iloc[0].to_dict()
                    kpi_data["total_defects"] = int(stats_row.get("count", 0))
                    kpi_data["avg_age_all"] = float(stats_row.get("avg_age", 0.0))
                    kpi_data["p90_age"] = float(stats_row.get("p90", 0.0))
                tbl = res.tables.get("defect_age")
                if tbl is not None and not tbl.empty and {"resolved_at", "age_days"}.issubset(tbl.columns):
                    closed_mask = tbl["resolved_at"].notna()
                    if closed_mask.any():
                        try:
                            kpi_data["avg_age_closed"] = float(tbl.loc[closed_mask, "age_days"].mean())
                        except Exception:
                            pass

            elif mid == "cumulative_open_closed":
                summary_tbl = res.tables.get("summary")
                if summary_tbl is not None and not summary_tbl.empty:
                    row = summary_tbl.iloc[0].to_dict()
                    kpi_data["opened_defects"] = int(row.get("opened_cum", 0))
                    kpi_data["closed_defects"] = int(row.get("closed_cum", 0))
                    if kpi_data["total_defects"] is None:
                        kpi_data["total_defects"] = kpi_data["opened_defects"]

            elif mid == "leakage_rate":
                overall_tbl = res.tables.get("leakage_overall")
                legacy_tbl = res.tables.get("leakage_overall_kpis")
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
                    kpi_data["leakage_pct"] = float(rate) if isinstance(rate, (int, float)) else None
                    kpi_data["leaked_count"] = int(leaked_v) if isinstance(leaked_v, (int, float)) else None
                    if kpi_data["total_defects"] is None:
                        kpi_data["total_defects"] = int(total_v) if isinstance(total_v, (int, float)) else None

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
                rej_tbl = res.tables.get("rejection_summary")
                if rej_tbl is None or rej_tbl.empty:
                    alt_tbl = res.tables.get("summary")
                    if alt_tbl is not None and not alt_tbl.empty:
                        rej_tbl = alt_tbl
                if rej_tbl is not None and not rej_tbl.empty:
                    rej_row = rej_tbl.iloc[0].to_dict()
                    kpi_data["rejection_pct"] = float(rej_row.get("rejection_percent", 0)) if isinstance(rej_row.get("rejection_percent"), (int, float)) else None
                    rejected_val = rej_row.get("rejected", 0)
                    total_val = rej_row.get("total", None)
                    kpi_data["rejected_count"] = int(rejected_val) if isinstance(rejected_val, (int, float)) else None
                    if kpi_data["total_defects"] is None and isinstance(total_val, (int, float)):
                        kpi_data["total_defects"] = int(total_val)

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

        # Second pass: build figures
        metric_objs = {mid: METRICS[mid]() for mid in metric_order if mid in METRICS}
        for mid in metric_order:
            res = result.metrics_results.get(mid)
            if res is None:
                continue
            metric_obj = metric_objs.get(mid)
            if metric_obj is None:
                continue
            fig_html = metric_obj.build_figure(res)
            if fig_html:
                prefix = extra_fragments.get(mid, "")
                if mid == "leakage_rate":
                    fig_html = f'<div class=""><div class="inner">{fig_html}</div></div>'
                figures[mid] = prefix + fig_html

        return figures, extra_fragments, kpi_data

    def _build_summary_kpis(self, kpi_data: Dict) -> str:
        """Build summary KPI card HTML."""
        if kpi_data["total_defects"] is None:
            return ""

        def fmt_days(v: Optional[float]) -> str:
            if v is None:
                return "-"
            try:
                return f"{v:.1f}d".replace(".0d", "d")
            except Exception:
                return "-"

        def pct_fmt(v: Optional[float]) -> str:
            if v is None:
                return "-"
            try:
                s = f"{v:.1f}".rstrip("0").rstrip(".")
                return s
            except Exception:
                return str(v)

        # Calculate open percentage
        open_pct = None
        if kpi_data["closed_defects"] is not None and kpi_data["total_defects"]:
            open_count = kpi_data["total_defects"] - kpi_data["closed_defects"]
            if kpi_data["total_defects"] > 0:
                open_pct = round(open_count / kpi_data["total_defects"] * 100.0, 1)

        open_block = "-"
        if open_pct is not None and kpi_data["closed_defects"] is not None:
            open_count = kpi_data["total_defects"] - kpi_data["closed_defects"]
            open_block = f"{pct_fmt(open_pct)}% ({open_count} bugs)"

        leakage_block = "-"
        if kpi_data["leakage_pct"] is not None:
            leak_pct_disp = pct_fmt(kpi_data["leakage_pct"])
            if kpi_data["leaked_count"] is not None:
                leakage_block = f"{leak_pct_disp}% ({kpi_data['leaked_count']} leaked)"
            else:
                leakage_block = f"{leak_pct_disp}%"

        rejection_block = "-"
        if kpi_data["rejection_pct"] is not None:
            rej_pct_disp = pct_fmt(kpi_data["rejection_pct"])
            if kpi_data["rejected_count"] is not None:
                rejection_block = f"{rej_pct_disp}% ({kpi_data['rejected_count']} rejected)"
            else:
                rejection_block = f"{rej_pct_disp}%"

        # Determine risk classes
        leakage_class = ""
        if kpi_data["leakage_pct"] is not None:
            if kpi_data["leakage_pct"] > 10:
                leakage_class = " risk-high"
            elif kpi_data["leakage_pct"] > 5:
                leakage_class = " risk-warn"
            else:
                leakage_class = " risk-ok"

        rejection_class = ""
        if kpi_data["rejection_pct"] is not None:
            if kpi_data["rejection_pct"] > 20:
                rejection_class = " risk-high"
            elif kpi_data["rejection_pct"] > 10:
                rejection_class = " risk-warn"
            else:
                rejection_class = " risk-ok"

        return (
            "<div class='card'><h2>Summary KPIs</h2><div class='kpi'>"
            f"<div class='item'><b>Total Defects</b><div>{kpi_data['total_defects']}</div></div>"
            f"<div class='item'><b>Open</b><div>{open_block}</div></div>"
            f"<div class='item{leakage_class}'><b>Leakage</b><div>{leakage_block}</div></div>"
            f"<div class='item{rejection_class}'><b>Rejection</b><div>{rejection_block}</div></div>"
            f"<div class='item'><b>Avg Age</b><div>{fmt_days(kpi_data['avg_age_all'])}</div></div>"
            f"<div class='item'><b>Avg Closed Age</b><div>{fmt_days(kpi_data['avg_age_closed'])}</div></div>"
            "</div></div>"
        )
    
    def _build_data_profile(self, profile: "DataProfile") -> str:
        """Build data profile card HTML showing AI classifications."""
        if not profile:
            return ""
        
        lines = [f"<div class='card'><h2>🤖 AI Data Understanding <span class='confidence'>({profile.overall_confidence:.0%} confidence)</span></h2>"]
        
        # Status classification
        if profile.status_profile:
            sp = profile.status_profile
            lines.append("<div class='profile-section'>")
            lines.append(f"<h4>Status Classification ({sp.method_used})</h4>")
            
            if sp.open_statuses:
                lines.append("<div><b>Open:</b> ")
                for s in sp.open_statuses:
                    lines.append(f"<span class='badge'>{s}</span>")
                lines.append("</div>")
            
            if sp.closed_statuses:
                lines.append("<div><b>Closed:</b> ")
                for s in sp.closed_statuses:
                    lines.append(f"<span class='badge'>{s}</span>")
                lines.append("</div>")
            
            if sp.rejected_statuses:
                lines.append("<div><b>Rejected:</b> ")
                for s in sp.rejected_statuses:
                    lines.append(f"<span class='badge'>{s}</span>")
                lines.append("</div>")
            
            if sp.warnings:
                lines.append("<div style='margin-top:8px;color:#dc2626;font-size:0.8rem'>")
                for warning in sp.warnings:
                    lines.append(f"⚠ {warning}<br>")
                lines.append("</div>")
            
            lines.append("</div>")
        
        # Environment classification
        if profile.environment_profile:
            ep = profile.environment_profile
            if ep.all_environments:
                lines.append("<div class='profile-section'>")
                lines.append(f"<h4>Environments ({ep.method_used})</h4>")
                lines.append(f"<div><b>Discovered:</b> {', '.join(ep.all_environments)}</div>")
                if ep.production_envs:
                    lines.append(f"<div><b>Production:</b> {', '.join(ep.production_envs)}</div>")
                lines.append("</div>")
        
        # Metric applicability
        if profile.missing_requirements:
            lines.append("<div class='profile-section'>")
            lines.append("<h4>⚠ Metrics with Missing Data</h4>")
            for metric_id, fields in profile.missing_requirements.items():
                lines.append(f"<div>• <b>{metric_id}:</b> missing {', '.join(fields)}</div>")
            lines.append("</div>")
        
        lines.append("</div>")
        
        return "".join(lines)

    def _format_insights(self, insights: Dict[str, str]) -> Dict[str, str]:
        """Format all metric insights."""
        formatted = {}
        for mid, txt in insights.items():
            fmt = self._format_insight(txt, heading="Insight")
            if fmt:
                formatted[mid] = fmt
        return formatted

    def _format_insight(self, text: str, heading: Optional[str] = "Insight") -> str:
        """Render LLM markdown preserving section grouping."""
        if not text or not text.strip():
            return ""

        lines = [l.rstrip() for l in text.splitlines()]
        sections: list[dict] = []
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
                if current["title"] is not None or current["paras"] or current["bullets"] or current["ordered"]:
                    sections.append(current)
                    current = {"title": None, "paras": [], "bullets": [], "ordered": []}
                current["title"] = stripped.lstrip("#").strip()
                continue

            # Unordered bullet
            if stripped.startswith("-") or stripped.startswith("*"):
                push_para()
                bullet_body = stripped[1:].lstrip()
                if all(ch == '-' for ch in bullet_body) and len(bullet_body) <= 3:
                    continue
                if bullet_body in {"--", "---"}:
                    continue
                if bullet_body.replace("-", "").strip() == "":
                    continue
                current["bullets"].append(bullet_body)
                continue

            # Ordered bullet
            if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == '.':
                push_para()
                item_text = stripped[2:].strip()
                if item_text and item_text not in {"--", "---"}:
                    current["bullets"].append(item_text)
                continue

            # Bold-only line
            if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
                push_para()
                current["bullets"].append(stripped)
                continue

            # Default text
            para_buf.append(stripped)

        push_para()
        if current["title"] is not None or current["paras"] or current["bullets"] or current["ordered"]:
            sections.append(current)

        def _apply_inline_markdown(s: str) -> str:
            import re
            out = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{m.group(1).strip()}</strong>", s)
            out = re.sub(r"\*{2,}", "", out)
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
        html_parts.append("</div>")
        return "".join(html_parts)
