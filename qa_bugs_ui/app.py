"""Streamlit web UI for QA Bugs Analytics."""
import streamlit as st
import pandas as pd
import yaml
from pathlib import Path
from datetime import datetime
import os
import sys

# Add parent directory to path to import qa_bugs modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from qa_bugs.services import AnalysisService, AnalysisConfig, get_storage_service
from qa_bugs_ui.components.results_display import display_results


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
    # Use configs from the main configs/ folder (same as CLI)
    config_path = Path(__file__).parent.parent / "configs" / config_file
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

        st.divider()

        st.header("🔒 Data Security")
        st.warning("""
        **Important:**
        - Anonymize sensitive data before upload
        - LLM processing enabled
        - No data stored permanently
        """)

    # Main content area
    st.subheader("📤 Upload File")
    uploaded_file = st.file_uploader(
        "Upload JIRA CSV File (anonymized, no PII, max 5MB)",
        type=["csv"],
        help="Upload a CSV export from JIRA. Maximum file size: 5MB. Ensure sensitive data is removed or anonymized."
    )

    if uploaded_file is not None:
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

        # Display file info
        st.success(f"✓ File uploaded: **{uploaded_file.name}** ({file_size_mb:.2f} MB)")

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
            st.info(f"Loaded **{len(df):,}** records from CSV")

        except Exception as e:
            st.error(f"Failed to parse CSV: {str(e)}")
            return

        # Show preview
        with st.expander("Preview Data (first 10 rows)"):
            st.dataframe(df.head(10), use_container_width=True)

        # Date range filters (optional)
        st.subheader("Filters (Optional)")
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

        # Run analysis button
        if st.button("🚀 Run Analysis", type="primary", use_container_width=True):
            with st.spinner("Running analysis... This may take a minute."):
                try:
                    # Run analysis
                    service = AnalysisService(config)
                    result = service.run_analysis(
                        df=df,
                        since=since_date.strftime("%Y-%m-%d") if since_date else None,
                        until=until_date.strftime("%Y-%m-%d") if until_date else None,
                        llm_enabled=True
                    )

                    # Store result in session state for persistence during reruns
                    st.session_state['analysis_result'] = result
                    st.session_state['analysis_timestamp'] = datetime.now()

                    st.success("✓ Analysis complete!")

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
