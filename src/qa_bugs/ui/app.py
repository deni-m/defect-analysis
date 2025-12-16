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

# Add parent directory to path to import qa_bugs modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from qa_bugs.services import AnalysisService, AnalysisConfig, get_storage_service
from qa_bugs.ingest.field_mapper import FieldMappingService
from qa_bugs.ui.components.results_display import display_results


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
st.set_page_config(
    page_title="QA Bugs Analytics",
    page_icon="🐛",
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
    st.title("🐛 QA Bugs Analytics")
    st.markdown("""
    Upload your JIRA CSV export to analyze defects and generate insights.
    """)

    # Initialize session state for controlling expanders
    if 'analysis_started' not in st.session_state:
        st.session_state['analysis_started'] = False

    # Security warning
    st.warning("""
    ⚠️ **Data Privacy Notice**

    - **Do NOT upload files containing sensitive personal data** (PII, credentials, etc.)
    - Uploaded data will be processed by AI models (LLM) for insights generation
    - Data may traverse non-secured infrastructure during processing
    - Ensure your CSV files are anonymized and comply with your organization's data policies
    """)

    # Sidebar for additional info
    with st.sidebar:
        st.header("About")
        st.info("""
        This tool analyzes JIRA defect data and provides:
        - Defect age distribution
        - Leakage rate analysis
        - Rejection rate tracking
        - Cumulative open/closed trends
        - Status by severity breakdown
        - Environment & priority analysis
        - AI-powered insights
        """)

        st.header("Configuration")
        config = load_config()
        st.write(f"**Enabled Metrics:** {len(config.enabled_metrics)}")
        st.write(f"**LLM Insights:** {'✓ Enabled' if config.llm.enabled else '✗ Disabled'}")
        
        # Auto-mapping toggle
        st.divider()
        st.header("⚙️ Field Mapping")
        
        auto_map_enabled = st.checkbox(
            "Auto-detect fields",
            value=True,  # Enabled by default
            help="Use AI to automatically detect field mapping from CSV headers"
        )
        
        if auto_map_enabled:
            st.info("""
            **Auto-mapping enabled:**
            - LLM will analyze your CSV headers
            - Required fields must be detected
            - Analysis won't start if fields missing
            """)
        else:
            st.info("""
            **Manual mapping:**
            - Using config file mapping
            - Ensure fields_mapping is configured
            """)

        st.divider()

        st.header("🔒 Data Security")
        st.warning("""
        **Important:**
        - Anonymize sensitive data before upload
        - LLM processing enabled
        - No data stored permanently
        """)

    # Main content area
    st.info("""
    **📋 Required CSV Fields:**
    Your CSV file must contain columns that can be mapped to these fields:
    
    **Core fields (always required):**
    - **key** - Unique defect/issue identifier
    - **created_at** - Creation date/timestamp
    - **status** - Current status (e.g., Open, Closed, In Progress)
    - **priority** - Priority level (e.g., High, Medium, Low)
    
    **Required for specific metrics:**
    - **resolved_at** - Resolution date (needed for: defect_age, cumulative_open_closed, age_by_priority)
    - **environment** - Environment where defect found (needed for: leakage_rate, defects_by_env_priority)
    """)
    
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
        # Collapse automatically after analysis runs
        show_config_expanded = not st.session_state.get('analysis_started', False)
        
        # Handle field mapping
        final_config = config
        mapping_result = None
        
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
                mapping_result = st.session_state['field_mapping_result']
                logging.info(f"Using cached field mapping for: {uploaded_file.name}")
        
        with st.expander("⚙️ Data Upload, Field Mapping & Filters", expanded=show_config_expanded):
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

        # Run analysis button (outside the expander)
        if st.button("🚀 Run Analysis", type="primary", use_container_width=True):
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
