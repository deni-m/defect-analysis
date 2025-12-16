"""Results display components for Streamlit UI."""
import streamlit as st
from typing import Optional
from qa_bugs.services.models import AnalysisResult, AnalysisConfig
from qa_bugs.services.kpi_calculator import SummaryKPIs
from qa_bugs.metrics import METRICS


def _display_summary_kpis(kpis: SummaryKPIs):
    """
    Display summary KPIs panel from pre-computed values.

    Args:
        kpis: Pre-computed SummaryKPIs from AnalysisResult
    """
    if kpis.total_defects is None:
        return

    # Helper functions
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
            return f"{s}%"
        except Exception:
            return "-"

    # Format display values
    open_count = None
    if kpis.closed_defects is not None and kpis.total_defects:
        open_count = kpis.total_defects - kpis.closed_defects

    open_block = "-"
    if kpis.open_pct is not None and open_count is not None:
        open_block = f"{pct_fmt(kpis.open_pct)} ({open_count} bugs)"

    leakage_block = "-"
    if kpis.leakage_pct is not None:
        leak_pct_disp = pct_fmt(kpis.leakage_pct)
        if kpis.leaked_count is not None:
            leakage_block = f"{leak_pct_disp} ({kpis.leaked_count} leaked)"
        else:
            leakage_block = f"{leak_pct_disp}"

    rejection_block = "-"
    if kpis.rejection_pct is not None:
        rej_pct_disp = pct_fmt(kpis.rejection_pct)
        if kpis.rejected_count is not None:
            rejection_block = f"{rej_pct_disp} ({kpis.rejected_count} rejected)"
        else:
            rejection_block = f"{rej_pct_disp}"

    # Determine risk classes
    leakage_class = ""
    if kpis.leakage_pct is not None:
        if kpis.leakage_pct > 10:
            leakage_class = "risk-high"
        elif kpis.leakage_pct > 5:
            leakage_class = "risk-warn"
        else:
            leakage_class = "risk-ok"

    rejection_class = ""
    if kpis.rejection_pct is not None:
        if kpis.rejection_pct > 20:
            rejection_class = "risk-high"
        elif kpis.rejection_pct > 10:
            rejection_class = "risk-warn"
        else:
            rejection_class = "risk-ok"

    # Create HTML for KPI panel
    kpi_html = f"""
    <style>
        .kpi-grid {{
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
            margin: 0 0 20px 0;
        }}
        .kpi-item {{
            flex: 1 1 150px;
            background: #f1f5f9;
            border-radius: 10px;
            padding: 12px;
            min-width: 120px;
        }}
        .kpi-item.risk-warn {{
            background: #fff4e6;
            border: 1px solid #ffb347;
        }}
        .kpi-item.risk-high {{
            background: #ffe5e5;
            border: 1px solid #ff6b6b;
        }}
        .kpi-item.risk-ok {{
            background: #e6f9ed;
            border: 1px solid #34c759;
        }}
        .kpi-label {{
            display: block;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #334155;
            margin-bottom: 6px;
            font-weight: 600;
        }}
        .kpi-value {{
            font-size: 1.1rem;
            font-weight: 500;
            color: #0f172a;
        }}
    </style>
    <div class="kpi-grid">
        <div class="kpi-item">
            <span class="kpi-label">Total Defects</span>
            <div class="kpi-value">{kpis.total_defects:,}</div>
        </div>
        <div class="kpi-item">
            <span class="kpi-label">Open</span>
            <div class="kpi-value">{open_block}</div>
        </div>
        <div class="kpi-item {leakage_class}">
            <span class="kpi-label">Leakage</span>
            <div class="kpi-value">{leakage_block}</div>
        </div>
        <div class="kpi-item {rejection_class}">
            <span class="kpi-label">Rejection</span>
            <div class="kpi-value">{rejection_block}</div>
        </div>
        <div class="kpi-item">
            <span class="kpi-label">Avg Age</span>
            <div class="kpi-value">{fmt_days(kpis.avg_age_all)}</div>
        </div>
        <div class="kpi-item">
            <span class="kpi-label">Avg Closed Age</span>
            <div class="kpi-value">{fmt_days(kpis.avg_age_closed)}</div>
        </div>
    </div>
    """

    st.markdown(kpi_html, unsafe_allow_html=True)


def display_results(result: AnalysisResult, config: AnalysisConfig):
    """
    Display analysis results in Streamlit.

    Args:
        result: AnalysisResult from analysis service
        config: AnalysisConfig used for analysis
    """
    # Display overall summary if available
    if result.overall_summary:
        st.subheader("🤖 AI Summary")
        with st.container(border=True):
            # Display pre-computed summary KPIs inside AI Summary
            if result.summary_kpis:
                _display_summary_kpis(result.summary_kpis)

            st.markdown(result.overall_summary)

    # Display each metric
    st.subheader("📈 Detailed Metrics")

    for metric_id in config.enabled_metrics:
        if metric_id not in result.metrics_results:
            continue

        metric_result = result.metrics_results[metric_id]

        # Get metric display name
        metric_obj = METRICS.get(metric_id)
        if metric_obj:
            display_name = getattr(metric_obj(), "display_name", metric_id)
        else:
            display_name = metric_id

        # Create expandable section for each metric
        with st.expander(f"**{display_name}**", expanded=True):
            # Render figure if available
            fig_html = None
            if metric_obj:
                try:
                    fig_html = metric_obj().build_figure(metric_result)
                except Exception as e:
                    st.error(f"Error building figure: {str(e)}")

            if fig_html:
                # Display HTML figure (Plotly charts)
                # Use taller height for cumulative metric (two stacked charts)
                height = 900 if metric_id == "cumulative_open_closed" else 500
                st.components.v1.html(
                    _wrap_figure_html(fig_html),
                    height=height,
                    scrolling=False
                )
            else:
                st.info("No visualization available for this metric.")

            # Display insight if available
            if metric_id in result.metric_insights:
                insight = result.metric_insights[metric_id]
                if insight:
                    st.markdown("**💡 Insights:**")
                    with st.container(border=True):
                        st.markdown(insight)

            # Display data tables (using toggle instead of expander to avoid nesting)
            if metric_result.tables:
                st.markdown("**📋 Data Tables:**")

                # Filter non-empty tables
                table_items = [(name, df) for name, df in metric_result.tables.items()
                               if df is not None and not df.empty]

                if table_items:
                    # Display toggles horizontally
                    cols = st.columns(len(table_items))
                    toggle_states = {}

                    for idx, (table_name, df) in enumerate(table_items):
                        with cols[idx]:
                            toggle_states[table_name] = st.toggle(
                                f"Show {table_name}",
                                key=f"{metric_id}_{table_name}"
                            )

                    # Display dataframes below toggles (only those toggled ON)
                    for table_name, df in table_items:
                        if toggle_states.get(table_name, False):
                            st.dataframe(df, use_container_width=True)


def _wrap_figure_html(fig_html: str) -> str:
    """
    Wrap figure HTML with necessary Plotly dependencies.

    Args:
        fig_html: HTML string containing Plotly figure

    Returns:
        Complete HTML with dependencies
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 10px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            }}
            .kpi {{
                display: flex;
                gap: 16px;
                flex-wrap: wrap;
                margin-bottom: 20px;
            }}
            .kpi .item {{
                flex: 1 1 150px;
                background: #f1f5f9;
                border-radius: 8px;
                padding: 12px;
            }}
            .kpi .item.risk-warn {{
                background: #fff4e6;
                border: 1px solid #ffb347;
            }}
            .kpi .item.risk-high {{
                background: #ffe5e5;
                border: 1px solid #ff6b6b;
            }}
            .kpi .item.risk-ok {{
                background: #e6f9ed;
                border: 1px solid #34c759;
            }}
            .kpi .item b {{
                display: block;
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #334155;
                margin-bottom: 4px;
            }}
        </style>
    </head>
    <body>
        {fig_html}
    </body>
    </html>
    """
