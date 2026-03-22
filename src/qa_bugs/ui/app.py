"""Streamlit web UI for QA Bugs Analytics."""
import streamlit as st
import pandas as pd
import yaml
import logging
from pathlib import Path
from datetime import datetime
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
# override=True ensures .env file takes priority over system environment variables
load_dotenv(override=True)

# Add src directory to path to import qa_bugs modules
# Works both locally and on Streamlit Cloud
project_root = Path(__file__).parent.parent.parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from qa_bugs.services import AnalysisService, AnalysisConfig, get_storage_service
from qa_bugs.ingest.field_mapper import FieldMappingService
from qa_bugs.ingest.env_value_mapper import EnvironmentValueMapper
from qa_bugs.ingest.normalizer import Normalizer
from qa_bugs.metrics import METRICS
from qa_bugs.ui.components.results_display import display_results
import base64


def get_base64_icon(icon_path: Path) -> str:
    """Convert icon file to base64 string for inline HTML display."""
    with open(icon_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def setup_logging(log_dir: Path):
    """Configure logging to file for UI session."""
    log_file = log_dir / "qa_bugs_ui.log"
    
    # File handler - detailed logs
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    
    logging.info(f"UI logging initialized. Log file: {log_file}")
    return log_file


# Page configuration
# Use bug.ico from ui/static folder
icon_path = Path(__file__).parent / "static" / "bug.ico"

st.set_page_config(
    page_title="QA Bugs Analytics",
    page_icon=str(icon_path) if icon_path.exists() else "🐛",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def load_config(config_file: str = "example.config.yml"):
    """
    Load analysis configuration from YAML file.

    Uses the same configs/ folder as CLI for consistency.
    """
    # Navigate to project root (src/qa_bugs/ui/app.py -> project root is 3 levels up)
    project_root = Path(__file__).parent.parent.parent.parent
    config_path = project_root / "configs" / config_file
    with open(config_path, "r", encoding="utf-8") as f:
        config_dict = yaml.safe_load(f)
    return AnalysisConfig.from_yaml_dict(config_dict)


def get_secret(key: str, default=None):
    """
    Get secret from Streamlit secrets or environment variable.

    Works both locally (.streamlit/secrets.toml) and on Streamlit Cloud.
    """
    # Try Streamlit secrets first
    try:
        if key in st.secrets:
            return st.secrets[key]
    except (FileNotFoundError, KeyError):
        pass

    # Fall back to environment variable
    return os.getenv(key, default)


def main():
    """Main Streamlit application."""
    # Display icon and title together
    from pathlib import Path
    icon_path = Path(__file__).parent / "static" / "bug.ico"
    
    # Use markdown with inline image for better alignment
    if icon_path.exists():
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 15px;">
                <img src="data:image/x-icon;base64,{get_base64_icon(icon_path)}" width="40" style="margin-bottom: 10px;">
                <h1 style="margin: 0;">QA Bugs Analytics</h1>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.title("🐛 QA Bugs Analytics")
    
    st.markdown("Upload your JIRA CSV export to analyze defects and generate insights.")
    st.markdown("---")

    # Initialize session state for controlling expanders
    if 'analysis_started' not in st.session_state:
        st.session_state['analysis_started'] = False

    # Sidebar for additional info
    with st.sidebar:
        st.header("⚠️ Data Privacy Notice")
        st.warning("""
        - **Do NOT upload files containing sensitive personal data** (PII, credentials, etc.)
        - Uploaded data will be processed by AI models (LLM) for insights generation
        - Data may traverse non-secured infrastructure during processing
        """)

        st.divider()
        
        st.header("📋 Quick Reference")
        st.info("""
        **Your CSV needs these fields:**
        - key
        - created_at
        - status
        - priority
        - resolved_at
        - environment
        """)
        
        st.page_link("pages/guide.py", label="View User Guide", icon="📖")

    # Load config for use in analysis
    config = load_config()

    # Main content area
    uploaded_file = st.file_uploader(
        "📤 Upload JIRA CSV File (anonymized, no PII, max 5MB)",
        type=["csv"],
        help="Upload a CSV export from JIRA. Maximum file size: 5MB. Ensure sensitive data is removed or anonymized."
    )

    if uploaded_file is not None:
        # Reset analysis state when new file is uploaded
        if 'last_uploaded_file' not in st.session_state or st.session_state['last_uploaded_file'] != uploaded_file.name:
            st.session_state['analysis_started'] = False
            st.session_state['last_uploaded_file'] = uploaded_file.name
            st.session_state['has_mapping_issues'] = False  # Reset mapping issues flag
            if 'analysis_result' in st.session_state:
                del st.session_state['analysis_result']
        
        # Validate file size (5MB limit)
        max_size_mb = 5
        max_size_bytes = max_size_mb * 1024 * 1024
        file_size_mb = uploaded_file.size / (1024 * 1024)

        if uploaded_file.size > max_size_bytes:
            st.error(f"""
            ❌ **File too large!**

            - Your file: **{file_size_mb:.2f} MB**
            - Maximum allowed: **{max_size_mb} MB**

            Please reduce file size by:
            - Filtering by date range in JIRA before export
            - Removing unnecessary columns
            - Splitting into multiple smaller files
            """)
            return

        # Optional: Upload to Azure Blob Storage (only if configured)
        # Disabled by default - analysis works in-memory without Azure
        azure_storage_enabled = False  # Set to True to enable Azure upload

        if azure_storage_enabled and get_secret("AZURE_STORAGE_CONNECTION_STRING"):
            with st.spinner("Uploading to Azure Storage..."):
                try:
                    storage = get_storage_service()
                    file_bytes = uploaded_file.getvalue()

                    blob_name, blob_url = storage.upload_csv(
                        file_content=file_bytes,
                        original_filename=uploaded_file.name,
                        metadata={
                            "uploaded_via": "streamlit",
                            "upload_time": datetime.now().isoformat()
                        }
                    )

                    st.success(f"✓ File saved to Azure Storage: `{blob_name}`")

                except Exception as e:
                    st.warning(f"Azure Storage upload failed: {str(e)}")

        # Load CSV data
        try:
            # Read from uploaded file directly (already in memory)
            df = pd.read_csv(uploaded_file)

        except Exception as e:
            st.error(f"Failed to parse CSV: {str(e)}")
            return

        # Master collapsible section for all configuration (can be hidden for PDF export)
        # Collapsed by default, expanded only if there are mapping errors/warnings
        has_mapping_issues = False
        
        # Handle field mapping
        final_config = config
        mapping_result = None
        
        # Auto-mapping is enabled by default
        auto_map_enabled = True
        
        # Cache field mapping detection in session state
        if auto_map_enabled:
            # Generate a cache key based on file name and columns
            cache_key = f"{uploaded_file.name}_{','.join(df.columns[:5])}"  # Use first 5 columns as part of key
            
            # Only run field mapping if not cached or file changed
            if 'field_mapping_cache_key' not in st.session_state or st.session_state['field_mapping_cache_key'] != cache_key:
                with st.spinner("Analyzing CSV headers..."):
                    # Create output directory for this session
                    from pathlib import Path
                    project_root = Path(__file__).parent.parent.parent.parent
                    output_dir = project_root / "output" / f"ui_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Setup logging
                    log_file = setup_logging(output_dir)
                    logging.info(f"Auto-mapping CSV with {len(df.columns)} columns")
                    
                    # Initialize LLM service if needed
                    llm_service = None
                    if config.llm.enabled:
                        from qa_bugs.llm.service import LLMService
                        # Convert config to dict format
                        llm_dict = {
                            "enabled": True,
                            "prompts_dir": config.llm.prompts_dir,
                            "provider": config.llm.provider,
                            "endpoint": config.llm.endpoint,
                            "deployment": config.llm.deployment,
                            "api_version": config.llm.api_version,
                            "temperature": 0.1,  # Lower temperature for mapping
                            "max_tokens": 1000,
                            "debug": config.llm.debug,
                            "log_prompts": config.llm.log_prompts,
                        }
                        llm_service = LLMService(llm_dict, log_dir=str(output_dir))
                    
                    # Initialize field mapper
                    field_mapper = FieldMappingService(llm_service=llm_service)
                    
                    # Auto-detect mapping
                    mapping_result = field_mapper.auto_detect_mapping(
                        df=df,
                        sample_rows=config.auto_mapping.sample_rows
                    )
                    
                    # Cache the result
                    st.session_state['field_mapping_result'] = mapping_result
                    st.session_state['field_mapping_cache_key'] = cache_key
                    logging.info(f"Field mapping cached for file: {uploaded_file.name}")
            else:
                # Use cached result
                mapping_result = st.session_state.get('field_mapping_result')
                logging.info(f"Using cached field mapping for: {uploaded_file.name}")
        
        # Expand section if there are validation errors or missing required fields
        has_errors = bool(
            auto_map_enabled
            and mapping_result
            and (
                (not mapping_result.valid)
                or bool(mapping_result.missing_required)
                or bool(mapping_result.errors)
            )
        )
        with st.expander("⚙️ Data Upload, Field Mapping & Filters", expanded=has_errors):
            # File info section
            st.markdown("### 📤 Upload Information")
            st.success(f"✓ File uploaded: **{uploaded_file.name}** ({file_size_mb:.2f} MB)")
            st.info(f"Loaded **{len(df):,}** records from CSV")
            
            st.divider()
            
            # Data preview section (collapsed by default)
            st.markdown("### 📋 Data Preview")
            show_preview = st.toggle("Show data preview", value=False)
            if show_preview:
                st.dataframe(df.head(10), use_container_width=True)
            
            st.divider()
            
            # Field mapping section
            if auto_map_enabled and mapping_result:
                st.markdown("### 🔍 Field Mapping Detection")
                
                # Display mapping result
                if mapping_result.valid:
                    st.success("✅ Field mapping detected successfully!")
                    logging.info(f"Field mapping valid: {len(mapping_result.mapping)} fields mapped")
                    
                    # Show detected mapping in collapsible table (collapsed by default)
                    show_mapping = st.toggle("Show detected field mapping", value=False)
                    if show_mapping:
                        mapping_df = pd.DataFrame([
                            {"Canonical Field": k, "CSV Column": v}
                            for k, v in mapping_result.mapping.items()
                        ])
                        st.dataframe(mapping_df, use_container_width=True, hide_index=True)
                    
                    # Show warnings if any
                    if mapping_result.warnings:
                        st.markdown("**⚠️ Warnings:**")
                        for warning in mapping_result.warnings:
                            st.warning(warning)
                    
                    # Override config with detected mapping
                    final_config = AnalysisConfig(
                        project=config.project,
                        fields_mapping=mapping_result.mapping,
                        auto_mapping=config.auto_mapping,
                        auto_env_mapping=config.auto_env_mapping,
                        env_value_mapping=config.env_value_mapping,
                        enabled_metrics=config.enabled_metrics,
                        metric_params=config.metric_params,
                        exclude_statuses=config.exclude_statuses,
                        llm=config.llm
                    )
                else:
                    # Show validation errors
                    st.error("❌ Field Mapping Validation Failed")
                    
                    if mapping_result.errors:
                        st.markdown("**Errors:**")
                        for error in mapping_result.errors:
                            st.error(f"• {error}")
                    
                    if mapping_result.missing_required:
                        st.markdown("**Missing Required Fields:**")
                        st.error(f"{', '.join(mapping_result.missing_required)}")
                        st.info("""
                        **Action Required:**
                        1. Check your CSV file has these columns
                        2. Or disable auto-mapping and use manual config
                        3. Or fix field names in your CSV export
                        """)
                        
                        if mapping_result.warnings:
                            st.markdown("**Warnings:**")
                            for warning in mapping_result.warnings:
                                st.warning(f"• {warning}")
                        
                        # Stop here - don't allow analysis
                        st.stop()
            
            st.divider()
            
            # Environment value mapping section
            env_mapping_result = None
            auto_map_env_enabled = True  # Enabled by default
            if auto_map_env_enabled:
                st.markdown("### 🌍 Environment Value Mapping")
                
                # Extract environment column from raw DF (before any normalization)
                # We need original values like "Production", not "PRODUCTION"
                env_col = final_config.fields_mapping.get('environment')
                if env_col and env_col in df.columns:
                    unique_envs = df[env_col].dropna().unique().tolist()
                    
                    if unique_envs:
                        # Cache environment mapping in session state
                        env_cache_key = f"{uploaded_file.name}_env_{','.join(sorted(unique_envs[:5]))}"
                        
                        if 'env_mapping_cache_key' not in st.session_state or st.session_state['env_mapping_cache_key'] != env_cache_key:
                            with st.spinner("Analyzing environment values..."):
                                # Initialize LLM service if needed (reuse if already created)
                                llm_service = None
                                if config.llm.enabled:
                                    from qa_bugs.llm.service import LLMService
                                    llm_dict = {
                                        "enabled": True,
                                        "prompts_dir": config.llm.prompts_dir,
                                        "provider": config.llm.provider,
                                        "endpoint": config.llm.endpoint,
                                        "deployment": config.llm.deployment,
                                        "api_version": config.llm.api_version,
                                        "temperature": 0.1,
                                        "max_tokens": 1000,
                                        "debug": config.llm.debug,
                                    }
                                    llm_service = LLMService(llm_dict)
                                
                                # Initialize environment mapper
                                env_mapper = EnvironmentValueMapper(
                                    llm_service=llm_service,
                                    target_categories=getattr(config.auto_env_mapping, 'target_categories', None)
                                )
                                
                                # Auto-map values
                                env_mapping_result = env_mapper.auto_map_values(
                                    unique_values=unique_envs,
                                    allow_passthrough=getattr(config.auto_env_mapping, 'allow_passthrough', True)
                                )
                                
                                # Cache result
                                st.session_state['env_mapping_result'] = env_mapping_result
                                st.session_state['env_mapping_cache_key'] = env_cache_key
                                logging.info(f"Environment mapping cached for file: {uploaded_file.name}")
                        else:
                            # Use cached result
                            env_mapping_result = st.session_state['env_mapping_result']
                            logging.info(f"Using cached environment mapping for: {uploaded_file.name}")
                        
                        # Display mapping result
                        if env_mapping_result.success:
                            st.success(f"✅ Environment values mapped successfully ({env_mapping_result.method_used})!")
                            
                            # Show mappings (only transformations)
                            transformations = {k: v for k, v in env_mapping_result.value_mapping.items() if k.upper() != v}
                            if transformations:
                                show_env_mapping = st.toggle("Show environment value mappings", value=False)
                                if show_env_mapping:
                                    mapping_df = pd.DataFrame([
                                        {"Original Value": k, "Mapped To": v}
                                        for k, v in sorted(transformations.items())
                                    ])
                                    st.dataframe(mapping_df, use_container_width=True, hide_index=True)
                            else:
                                st.info("All environment values already in standard format (no transformations needed)")
                            
                            # Show warnings
                            if env_mapping_result.warnings:
                                for warning in env_mapping_result.warnings:
                                    st.warning(warning)
                            
                            # Update config with environment value mapping
                            final_config.env_value_mapping = env_mapping_result.value_mapping
                            logging.info(f"UI: Updated final_config.env_value_mapping with {len(env_mapping_result.value_mapping)} mappings")
                            logging.info(f"UI: Mapping details: {env_mapping_result.value_mapping}")
                        else:
                            st.error("❌ Environment value mapping failed")
                            for error in env_mapping_result.errors:
                                st.error(f"• {error}")
                    else:
                        st.info("No environment values found in data")
                else:
                    st.warning("⚠️ Environment column not found in data - skipping environment value mapping")
            
            st.divider()

            # Metric readiness check (cached, tied to file + mapping)
            readiness_cache_key = f"readiness_{cache_key}"
            if st.session_state.get('readiness_cache_key') != readiness_cache_key:
                temp_service = AnalysisService(final_config)
                st.session_state['missing_by_metric'] = temp_service.check_metric_readiness(df)
                st.session_state['readiness_cache_key'] = readiness_cache_key

            st.divider()

            # Date range filters section
            st.markdown("### ⚙️ Date Filters (Optional)")
            col1, col2 = st.columns(2)

            with col1:
                use_since = st.checkbox("Filter by start date")
                since_date = None
                if use_since:
                    since_date = st.date_input("Created since")

            with col2:
                use_until = st.checkbox("Filter by end date")
                until_date = None
                if use_until:
                    until_date = st.date_input("Created until")

        # Metric readiness warning (outside the expander)
        confirmed_partial = True
        missing_by_metric = st.session_state.get('missing_by_metric', {})
        if missing_by_metric:
            lines = []
            for mid, fields in missing_by_metric.items():
                name = METRICS[mid].display_name if mid in METRICS else mid
                lines.append(f"- **{name}**: missing `{', '.join(fields)}`")
            st.warning("⚠️ Some metrics will be skipped due to missing fields:\n\n" + "\n".join(lines))
            confirmed_partial = st.checkbox(
                "I understand — continue with the remaining metrics",
                key="confirm_partial_metrics"
            )

        # Run analysis button (outside the expander)
        run_disabled = bool(missing_by_metric) and not confirmed_partial
        if st.button("🚀 Run Analysis", type="primary", use_container_width=True, disabled=run_disabled):
            with st.spinner("Running analysis... This may take a minute."):
                try:
                    # Create output directory for this analysis run
                    from pathlib import Path
                    project_root = Path(__file__).parent.parent.parent.parent
                    output_dir = project_root / "output" / f"ui_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Setup logging
                    log_file = setup_logging(output_dir)
                    logging.info(f"Starting analysis run with {len(df)} records")
                    auto_classify_enabled = True  # Enabled by default
                    logging.info(f"Auto-classify enabled: {auto_classify_enabled}")
                    logging.info(f"Final config env_value_mapping: {final_config.env_value_mapping}")
                    logging.info(f"Final config fields_mapping: {final_config.fields_mapping}")
                    
                    # Update config with auto-classify toggle from UI
                    final_config.auto_classification.enabled = auto_classify_enabled
                    
                    # Run analysis with final config (may have updated mapping)
                    service = AnalysisService(final_config)
                    result = service.run_analysis(
                        df=df,
                        since=since_date.strftime("%Y-%m-%d") if since_date else None,
                        until=until_date.strftime("%Y-%m-%d") if until_date else None,
                        llm_enabled=True,
                        log_dir=str(output_dir)
                    )

                    # Store result in session state for persistence during reruns
                    st.session_state['analysis_result'] = result
                    st.session_state['analysis_timestamp'] = datetime.now()
                    
                    # Mark that analysis has started (will collapse expanders on rerun)
                    st.session_state['analysis_started'] = True

                    logging.info("Analysis completed successfully")
                    st.success("✓ Analysis complete!")
                    
                    # Force rerun to collapse expanders
                    st.rerun()

                except Exception as e:
                    st.error(f"Analysis failed: {str(e)}")
                    st.exception(e)
                    return

    # Display results if available
    if 'analysis_result' in st.session_state:
        st.divider()
        display_results(st.session_state['analysis_result'], config)


if __name__ == "__main__":
    main()
