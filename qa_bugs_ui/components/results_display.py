"""Results display components for Streamlit UI."""
import streamlit as st
from qa_bugs.services.models import AnalysisResult, AnalysisConfig
from qa_bugs.metrics import METRICS


def display_results(result: AnalysisResult, config: AnalysisConfig):
    """
    Display analysis results in Streamlit.

    Args:
        result: AnalysisResult from analysis service
        config: AnalysisConfig used for analysis
    """
    st.header("📊 Analysis Results")

    # Display metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Records", f"{result.metadata['total_records']:,}")
    with col2:
        st.metric("Filtered Records", f"{result.metadata['filtered_records']:,}")
    with col3:
        st.metric("Metrics Computed", len(result.metrics_results))

    # Display overall summary if available
    if result.overall_summary:
        st.subheader("🤖 AI Summary")
        with st.container(border=True):
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
