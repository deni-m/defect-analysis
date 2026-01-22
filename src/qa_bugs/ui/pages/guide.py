"""Guide page with detailed information about QA Bugs Analytics."""
import streamlit as st
from pathlib import Path
import base64


def get_base64_icon(icon_path: Path) -> str:
    """Convert icon file to base64 string for inline HTML display."""
    with open(icon_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def show():
    """Display the guide page."""
    # Display icon and title
    icon_path = Path(__file__).parent.parent / "static" / "bug.ico"
    
    if icon_path.exists():
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 15px;">
                <img src="data:image/x-icon;base64,{get_base64_icon(icon_path)}" width="40" style="margin-bottom: 10px;">
                <h1 style="margin: 0;">QA Bugs Analytics - User Guide</h1>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.title("🐛 QA Bugs Analytics - User Guide")

    st.markdown("---")

    # Table of Contents
    st.markdown("""
    ## 📑 Table of Contents
    - [Getting Started](#getting-started)
    - [CSV File Requirements](#csv-file-requirements)
    - [Field Mapping](#field-mapping)
    - [Environment Mapping](#environment-mapping)
    - [AI Data Classification](#ai-data-classification)
    - [Available Metrics](#available-metrics)
    - [Data Security](#data-security)
    - [Troubleshooting](#troubleshooting)
    """)

    st.markdown("---")

    # Getting Started
    st.header("🚀 Getting Started")
    st.markdown("""
    This tool analyzes JIRA defect data and provides comprehensive insights including:
    - Defect age distribution
    - Leakage rate analysis
    - Rejection rate tracking
    - Cumulative open/closed trends
    - Status by severity breakdown
    - Environment & priority analysis
    - AI-powered insights

    ### Quick Start Steps:
    1. **Prepare your CSV**: Export your JIRA issues to CSV format
    2. **Anonymize data**: Remove any sensitive personal information (PII)
    3. **Upload**: Use the file uploader on the main page
    4. **Configure**: Set date range and select metrics
    5. **Analyze**: Click "Run Analysis" to generate insights
    """)

    st.markdown("---")

    # CSV Requirements
    st.header("📋 CSV File Requirements")
    
    st.subheader("Core Fields (Always Required)")
    st.markdown("""
    Your CSV file must contain columns that can be mapped to these fields:

    | Field | Description | Example Values |
    |-------|-------------|----------------|
    | **key** | Unique defect/issue identifier | BUG-123, ISSUE-456 |
    | **created_at** | Creation date/timestamp | 2024-01-15, 2024-01-15 10:30:00 |
    | **status** | Current status | Open, Closed, In Progress, Resolved |
    | **priority** | Priority level | High, Medium, Low, Critical |
    """)

    st.subheader("Metric-Specific Fields")
    st.markdown("""
    Additional fields required for specific metrics:

    | Field | Required For | Description |
    |-------|-------------|-------------|
    | **resolved_at** | defect_age, cumulative_open_closed, age_by_priority | Resolution date/timestamp |
    | **environment** | leakage_rate, defects_by_env_priority | Environment where defect was found (e.g., PROD, QA, DEV) |
    """)

    st.info("""
    💡 **Tip**: Column names don't need to match exactly! The AI-powered field mapper can detect your 
    column names automatically. For example:
    - "Issue Key" → key
    - "Created Date" → created_at
    - "Resolution Date" → resolved_at
    """)

    st.markdown("---")

    # Field Mapping
    st.header("⚙️ Field Mapping")
    st.markdown("""
    ### Auto-detection (Recommended)
    When enabled, the system uses AI to automatically detect which columns in your CSV correspond 
    to required fields.

    **Benefits:**
    - ✓ No manual configuration needed
    - ✓ Works with any column naming convention
    - ✓ Validates that all required fields are present
    - ✓ Shows confidence scores for each mapping

    ### Manual Mapping
    If auto-detection is disabled, the system uses the field mapping from your configuration file 
    (`configs/example.config.yml`).

    **Configuration example:**
    ```yaml
    fields_mapping:
      key: "Issue key"
      summary: "Summary"
      created_at: "Created"
      resolved_at: "Resolved"
      status: "Status"
      priority: "Priority"
      environment: "Environment"
    ```
    """)

    st.markdown("---")

    # Environment Mapping
    st.header("🌍 Environment Value Mapping")
    st.markdown("""
    Environment values from your JIRA data can vary widely. The auto-mapper standardizes them 
    into common categories.

    ### Mapping Examples:

    | Original Value | Mapped To | Category |
    |---------------|-----------|----------|
    | production, prod, prd | PROD | Production |
    | quality, qa, test, testing | QA | Quality Assurance |
    | staging, stage, uat | STAGE | Staging |
    | development, dev | DEV | Development |

    ### How it Works:
    1. System extracts all unique environment values from your CSV
    2. AI analyzes each value and assigns it to a standard category
    3. Unmapped values are uppercased and kept as-is
    4. Results are cached for the session

    **When to disable:**
    - Your data already uses standardized environment names
    - You want to preserve exact values from JIRA
    """)

    st.markdown("---")

    # AI Data Classification
    st.header("🧠 AI Data Classification")
    st.markdown("""
    The AI Data Profiler goes beyond simple mapping to understand the semantic meaning of your data.

    ### What it Classifies:

    #### 1. Status Categories
    Automatically identifies which statuses represent:
    - **Open** states (e.g., "Open", "In Progress", "Reopened")
    - **Closed** states (e.g., "Closed", "Resolved", "Done")
    - **Rejected** states (e.g., "Rejected", "Won't Fix", "Duplicate")

    #### 2. Priority Ordering
    Determines the severity order of your priorities:
    - Highest severity (e.g., "Critical", "Blocker")
    - High (e.g., "High", "Major")
    - Medium (e.g., "Medium", "Normal")
    - Low (e.g., "Low", "Minor", "Trivial")

    #### 3. Environment Classification
    Identifies which environments are:
    - **Production** (customer-facing systems)
    - **Test/QA** (testing environments)
    - **Development** (development environments)

    ### Confidence Scores
    Each classification includes a confidence score (0-100%) indicating how certain the AI is about 
    the classification. Low confidence scores may indicate ambiguous or non-standard values.

    **Benefits:**
    - ✓ Works with custom JIRA workflows
    - ✓ No hardcoded lists to maintain
    - ✓ Adapts to your terminology
    - ✓ Transparent confidence scoring
    """)

    st.markdown("---")

    # Available Metrics
    st.header("📊 Available Metrics")
    
    st.subheader("Defect Age")
    st.markdown("""
    Analyzes how long defects remain open before resolution.
    - Age distribution histogram
    - Average, median, P90, P95 percentiles
    - Breakdown by current status
    """)

    st.subheader("Age by Priority")
    st.markdown("""
    Shows defect age distribution segmented by priority level.
    - Identifies if high-priority defects are resolved faster
    - Compares aging across priority categories
    """)

    st.subheader("Leakage Rate")
    st.markdown("""
    Measures defects found in production vs. pre-production environments.
    - Production defects percentage
    - Trend over time
    - Quality gate effectiveness indicator
    """)

    st.subheader("Rejection Rate")
    st.markdown("""
    Tracks defects rejected/closed without implementation.
    - Rejection percentage over time
    - Common rejection reasons
    - Efficiency indicator
    """)

    st.subheader("Cumulative Open/Closed")
    st.markdown("""
    Shows the cumulative number of defects opened and closed over time.
    - Trend lines for opened vs. closed
    - Backlog growth/reduction visibility
    - Velocity insights
    """)

    st.subheader("Status by Priority")
    st.markdown("""
    Distribution of defect statuses across priority levels.
    - Stacked bar charts
    - Focus areas identification
    - Priority vs. status heatmap
    """)

    st.subheader("Defects by Environment & Priority")
    st.markdown("""
    Cross-analysis of environments and priorities.
    - Where issues are found
    - Severity distribution by environment
    - Testing coverage insights
    """)

    st.markdown("---")

    # Data Security
    st.header("🔒 Data Security")
    st.warning("""
    ### Important Security Guidelines

    ⚠️ **What NOT to Upload:**
    - Files containing personal identifiable information (PII)
    - Customer names, emails, phone numbers
    - Credentials, API keys, passwords
    - Confidential business information
    - Unredacted error messages with sensitive data

    ✅ **What's Safe:**
    - Anonymized defect IDs
    - Generic status/priority values
    - Dates and timestamps
    - Sanitized environment names
    - Aggregated metrics

    ### How Data is Processed:
    1. **File Upload**: Stays in memory, not permanently stored
    2. **AI Processing**: May be sent to LLM API (Azure OpenAI) for analysis
    3. **Results**: Generated in-memory and displayed
    4. **Logs**: Stored locally in output/ directory (review before sharing)

    ### Best Practices:
    - Anonymize data before export from JIRA
    - Use generic identifiers (e.g., BUG-123 instead of customer names)
    - Review your CSV before upload
    - Follow your organization's data handling policies
    """)

    st.markdown("---")

    # Troubleshooting
    st.header("🔧 Troubleshooting")
    
    st.subheader("Common Issues")
    
    with st.expander("❌ 'Required field not found' error"):
        st.markdown("""
        **Cause**: Auto-mapper couldn't detect one or more required fields in your CSV.

        **Solutions**:
        1. Check if your CSV has the necessary columns
        2. Ensure column headers are in the first row
        3. Try manual mapping in configuration file
        4. Check that date columns contain valid dates
        """)

    with st.expander("❌ 'File too large' error"):
        st.markdown("""
        **Cause**: Uploaded file exceeds 5MB limit.

        **Solutions**:
        1. Filter by date range before exporting from JIRA
        2. Remove unnecessary columns
        3. Split analysis into multiple smaller time periods
        4. Export only relevant issue types
        """)

    with st.expander("❌ Date parsing errors"):
        st.markdown("""
        **Cause**: Date format not recognized by the system.

        **Solutions**:
        1. Ensure dates are in standard format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
        2. Check for empty/null date values
        3. Verify timezone information is consistent
        4. Try exporting with ISO format from JIRA
        """)

    with st.expander("❌ LLM/AI features not working"):
        st.markdown("""
        **Cause**: LLM API credentials not configured or quota exceeded.

        **Solutions**:
        1. Check that Azure OpenAI environment variables are set
        2. Verify API key is valid and not expired
        3. Check API quota/rate limits
        4. Try disabling LLM features temporarily
        5. Review logs in output/ directory for detailed error messages
        """)

    st.subheader("Getting Help")
    st.info("""
    📧 **Need more help?**
    - Check the project README.md for detailed documentation
    - Review configuration examples in configs/
    - Check logs in the output/ directory
    - Contact your team administrator
    """)

    st.markdown("---")

    # Back to main page button
    st.markdown("### 🏠 Ready to Analyze?")
    if st.button("← Back to Main Page", type="primary", use_container_width=True):
        st.switch_page("app.py")


if __name__ == "__main__":
    show()
