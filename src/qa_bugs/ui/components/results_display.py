"""Results display components for Streamlit UI."""
import streamlit as st
from typing import Optional
from qa_bugs.services.models import AnalysisResult, AnalysisConfig
from qa_bugs.services.kpi_calculator import SummaryKPIs
from qa_bugs.services.data_profiler import DataProfile, StatusProfile, PriorityProfile, EnvironmentProfile
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
    open_count = kpis.opened_defects
    if open_count is None and kpis.closed_defects is not None and kpis.total_defects:
        open_count = kpis.total_defects - kpis.closed_defects

    open_block = "-"
    if kpis.open_pct is not None and open_count is not None:
        open_block = f"{pct_fmt(kpis.open_pct)} ({open_count} bugs)"

    leakage_block = "-"
    leakage_class = "risk-na"
    if kpis.leakage_applicable is False:
        pass  # stay N/A
    elif kpis.leakage_pct is not None:
        leakage_class = ""
        leak_pct_disp = pct_fmt(kpis.leakage_pct)
        if kpis.leaked_count is not None:
            leakage_block = f"{leak_pct_disp} ({kpis.leaked_count} leaked)"
        else:
            leakage_block = f"{leak_pct_disp}"

    rejection_block = "N/A"
    rejection_class = "risk-na"
    if kpis.rejection_applicable is False:
        pass  # stay N/A
    elif kpis.rejection_pct is not None:
        rejection_class = ""
        rej_pct_disp = pct_fmt(kpis.rejection_pct)
        if kpis.rejected_count is not None:
            rejection_block = f"{rej_pct_disp} ({kpis.rejected_count} rejected)"
        else:
            rejection_block = f"{rej_pct_disp}"

    # Determine risk classes
    if kpis.leakage_applicable is not False and kpis.leakage_pct is not None:
        if kpis.leakage_pct > 10:
            leakage_class = "risk-high"
        elif kpis.leakage_pct > 5:
            leakage_class = "risk-warn"
        else:
            leakage_class = "risk-ok"

    if kpis.rejection_applicable is not False and kpis.rejection_pct is not None:
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
        .kpi-item.risk-na {{
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
        }}
        .kpi-item.risk-na .kpi-value {{
            color: #94a3b8;
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


def _display_data_profile(profile: DataProfile):
    """
    Display AI Data Profiler results in an expandable section.
    
    Args:
        profile: DataProfile containing AI-classified semantics
    """
    with st.expander("🧠 **AI Data Profile** - Semantic Understanding", expanded=False):
        st.markdown("""
        The AI Data Profiler automatically analyzed your data to understand its semantic meaning.
        This helps optimize metric calculations and provide better insights.
        """)
        
        # Overall confidence
        confidence_pct = profile.overall_confidence * 100
        confidence_color = "🟢" if confidence_pct >= 80 else "🟡" if confidence_pct >= 60 else "🔴"
        st.metric("Overall Confidence", f"{confidence_color} {confidence_pct:.0f}%")

        # Build tab list dynamically based on available profiles
        tab_defs = [("📊 Status", "status"), ("⚠️ Priority", "priority"), ("🌍 Environment", "environment")]
        if profile.resolution_profile:
            tab_defs.append(("🔄 Resolution", "resolution"))
        if profile.fix_version_profile:
            tab_defs.append(("🏷️ Fix Version", "fix_version"))
        if profile.category_profile:
            tab_defs.append(("📂 Category", "category"))
        tab_defs.append(("📋 Summary", "summary"))
        tab_defs.append(("🔍 Debug", "debug"))

        tab_labels = [t[0] for t in tab_defs]
        tab_keys = [t[1] for t in tab_defs]
        tabs = st.tabs(tab_labels)

        def _tab(key: str):
            return tabs[tab_keys.index(key)]

        # Status Profile Tab
        with _tab("status"):
            if profile.status_profile:
                sp = profile.status_profile
                st.markdown(f"**Classification Method:** {sp.method_used.upper()} (Confidence: {sp.confidence*100:.0f}%)")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown("**✅ Open Statuses**")
                    for status in sp.open_statuses:
                        st.markdown(f"- `{status}`")
                
                with col2:
                    st.markdown("**✔️ Closed Statuses**")
                    for status in sp.closed_statuses:
                        st.markdown(f"- `{status}`")
                
                with col3:
                    st.markdown("**❌ Rejected Statuses**")
                    for status in sp.rejected_statuses:
                        st.markdown(f"- `{status}`")
                
                if sp.warnings:
                    st.warning("⚠️ **Warnings:**\n" + "\n".join(f"- {w}" for w in sp.warnings))
            else:
                st.info("Status classification not performed")
        
        # Priority Profile Tab
        with _tab("priority"):
            if profile.priority_profile:
                pp = profile.priority_profile
                st.markdown(f"**Classification Method:** {pp.method_used.upper()} (Confidence: {pp.confidence*100:.0f}%)")
                
                st.markdown("**Severity Order** (Highest → Lowest):")
                for idx, priority in enumerate(pp.severity_order, 1):
                    emoji = "🔴" if idx == 1 else "🟠" if idx == 2 else "🟡" if idx == 3 else "🟢"
                    st.markdown(f"{idx}. {emoji} `{priority}`")
                
                if pp.warnings:
                    st.warning("⚠️ **Warnings:**\n" + "\n".join(f"- {w}" for w in pp.warnings))
            else:
                st.info("Priority classification not performed")
        
        # Environment Profile Tab
        with _tab("environment"):
            if profile.environment_profile:
                ep = profile.environment_profile
                st.markdown(f"**Classification Method:** {ep.method_used.upper()} (Confidence: {ep.confidence*100:.0f}%)")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**🚀 Production Environments**")
                    for env in ep.production_envs:
                        st.markdown(f"- `{env}`")
                
                with col2:
                    st.markdown("**🔧 Non-Production Environments**")
                    for env in ep.non_production_envs:
                        st.markdown(f"- `{env}`")
                
                st.markdown("**Pipeline Order** (Development → Production):")
                pipeline_str = " → ".join(f"`{env}`" for env in ep.pipeline_order)
                st.markdown(pipeline_str)
                
                if ep.warnings:
                    st.warning("⚠️ **Warnings:**\n" + "\n".join(f"- {w}" for w in ep.warnings))
            else:
                st.info("Environment classification not performed")

        # Resolution Profile Tab (only shown when resolution field is present)
        if profile.resolution_profile:
            with _tab("resolution"):
                rp = profile.resolution_profile
                st.markdown(f"**Classification Method:** {rp.method_used.upper()} (Confidence: {rp.confidence*100:.0f}%)")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown("**✅ Accepted Resolutions**")
                    for r in rp.accepted_resolutions:
                        st.markdown(f"- `{r}`")
                with col2:
                    st.markdown("**❌ Rejected Resolutions**")
                    for r in rp.rejected_resolutions:
                        st.markdown(f"- `{r}`")
                with col3:
                    st.markdown("**➖ Other / Unresolved**")
                    for r in rp.other_resolutions:
                        st.markdown(f"- `{r}`")

                if rp.warnings:
                    st.warning("⚠️ **Warnings:**\n" + "\n".join(f"- {w}" for w in rp.warnings))

        # Fix Version Profile Tab (only shown when fix_version field is present)
        if profile.fix_version_profile:
            with _tab("fix_version"):
                fvp = profile.fix_version_profile
                st.markdown(f"**Unique values:** {fvp.unique_count}  |  **Fill rate:** {fvp.completeness*100:.1f}%")
                if fvp.top_values:
                    import pandas as _pd
                    st.markdown("**Top Fix Versions by frequency:**")
                    st.dataframe(
                        _pd.DataFrame(fvp.top_values, columns=["Fix Version", "Count"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No fix version values found.")

        # Category Profile Tab (only shown when category field is present)
        if profile.category_profile:
            with _tab("category"):
                cp = profile.category_profile
                st.markdown(f"**Unique values:** {cp.unique_count}  |  **Fill rate:** {cp.completeness*100:.1f}%")
                if cp.top_values:
                    import pandas as _pd
                    st.markdown("**Top Categories by frequency:**")
                    st.dataframe(
                        _pd.DataFrame(cp.top_values, columns=["Category", "Count"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No category values found.")

        # Summary Tab
        with _tab("summary"):
            st.markdown("**📁 Available Fields:**")
            st.write(", ".join(f"`{field}`" for field in profile.available_fields))
            
            st.markdown("**📊 Field Completeness:**")
            completeness_data = [
                {"Field": field, "Completeness": f"{pct:.1f}%"}
                for field, pct in sorted(profile.field_completeness.items(), key=lambda x: x[1], reverse=True)
            ]
            st.dataframe(completeness_data, use_container_width=True, hide_index=True)
            
            if profile.date_range:
                st.markdown(f"**📅 Date Range:** {profile.date_range[0]} to {profile.date_range[1]}")
            
            if profile.applicable_metrics:
                st.markdown("**✅ Applicable Metrics:**")
                st.write(", ".join(f"`{m}`" for m in profile.applicable_metrics))
            
            if profile.missing_requirements:
                st.markdown("**⚠️ Missing Requirements for Some Metrics:**")
                for metric, reqs in profile.missing_requirements.items():
                    st.markdown(f"- `{metric}`: Missing {', '.join(f'`{r}`' for r in reqs)}")

        # Debug Tab — shows raw LLM prompts/responses for field mapping and env mapping
        with _tab("debug"):
            fm_result = st.session_state.get("field_mapping_result")
            env_result = st.session_state.get("env_mapping_result")

            st.markdown("### 🗂️ Field Mapping")
            if fm_result:
                method = getattr(fm_result, "method_used", "unknown")
                st.markdown(f"**Method:** `{method}`")

                if getattr(fm_result, "llm_error", None):
                    st.error(f"LLM error: {fm_result.llm_error}")

                st.markdown(f"**Final mapping ({len(fm_result.mapping)} fields):**")
                import pandas as _pd
                st.dataframe(
                    _pd.DataFrame(
                        [{"Canonical field": k, "CSV column": v} for k, v in fm_result.mapping.items()]
                    ),
                    use_container_width=True, hide_index=True,
                )

                if getattr(fm_result, "llm_prompt", None):
                    with st.expander("LLM prompt sent", expanded=False):
                        st.code(fm_result.llm_prompt, language="markdown")

                if getattr(fm_result, "llm_raw_response", None):
                    with st.expander("LLM raw response", expanded=True):
                        st.code(fm_result.llm_raw_response, language="yaml")
                elif method == "fuzzy":
                    st.info("Fuzzy matching was used — no LLM response available.")
            else:
                st.info("No field mapping result in session yet.")

            st.divider()
            st.markdown("### 🌍 Environment Value Mapping")
            if env_result:
                method = getattr(env_result, "method_used", "unknown")
                st.markdown(f"**Method:** `{method}`")

                if getattr(env_result, "llm_error", None):
                    st.error(f"LLM error: {env_result.llm_error}")

                if getattr(env_result, "llm_prompt", None):
                    with st.expander("LLM prompt sent", expanded=False):
                        st.code(env_result.llm_prompt, language="markdown")

                if getattr(env_result, "llm_raw_response", None):
                    with st.expander("LLM raw response", expanded=True):
                        st.code(env_result.llm_raw_response, language="yaml")
                elif method in ("fuzzy", "passthrough"):
                    st.info(f"Method was `{method}` — no LLM response available.")
            else:
                st.info("No environment mapping result in session yet.")


def display_results(result: AnalysisResult, config: AnalysisConfig):
    """
    Display analysis results in Streamlit.

    Args:
        result: AnalysisResult from analysis service
        config: AnalysisConfig used for analysis
    """
    # Display AI Data Profile if available (at the top)
    if result.data_profile:
        _display_data_profile(result.data_profile)
    
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
                # Use taller height for metrics that render multiple stacked charts.
                height = 900 if metric_id in {"cumulative_open_closed", "leakage_rate"} else 500
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
