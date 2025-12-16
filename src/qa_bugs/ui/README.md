# QA Bugs Analytics - Streamlit Web UI

Web interface for analyzing JIRA defect data with AI-powered insights.

## 🚀 Quick Start

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -e .
   ```

2. **Configure secrets:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # Edit .streamlit/secrets.toml with your Azure credentials
   ```

3. **Run the app:**
   ```bash
   streamlit run qa_bugs_ui/app.py
   ```

4. **Open browser:** http://localhost:8501

### Using Environment Variables (Alternative)

Instead of `.streamlit/secrets.toml`, you can set environment variables:

```bash
export AZURE_STORAGE_CONNECTION_STRING="your_connection_string"
export AZURE_STORAGE_CONTAINER="bug-analytics-uploads"
export AZURE_OPENAI_API_KEY="your_key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"

streamlit run qa_bugs_ui/app.py
```

## 📋 Features

- **File Upload**: Drag & drop JIRA CSV exports
- **Azure Storage**: Automatic file persistence to Azure Blob Storage
- **7 Metrics**: Comprehensive defect analysis
  - Defect Age Distribution
  - Leakage Rate (QA → Prod escapes)
  - Rejection Rate
  - Cumulative Open/Closed Trends
  - Status by Severity
  - Age by Priority
  - Defects by Environment & Priority
- **AI Insights**: Azure OpenAI-powered analysis
- **Interactive Charts**: Plotly visualizations
- **Data Preview**: Inspect uploaded data
- **Optional Filters**: Date range filtering

## 🎯 Usage

1. **Upload CSV**: Click "Upload JIRA CSV File" and select your export
2. **File Storage**: File is automatically saved to Azure Blob Storage
3. **Optional Filters**: Set date ranges if needed
4. **Run Analysis**: Click "🚀 Run Analysis" button
5. **View Results**: Explore metrics, charts, and AI insights

## ⚙️ Configuration

### Default Analysis Config

Located at `qa_bugs_ui/config/default.yml`

Customize for your JIRA instance:
- Field mappings (match your CSV columns)
- Metric parameters (environment names, etc.)
- LLM settings

### Supported CSV Format

Expected columns (configurable via field mappings):
- `Key` - Issue ID
- `Created` - Creation date
- `resolutiondate` - Resolution date
- `Status` - Current status
- `Priority` - Priority level
- `FixVersions` - Fix version
- `customfield_12200` - Environment (or your custom field)
- `Component` - Component/category

## 🔐 Required Secrets

| Secret | Description |
|--------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Azure Storage account connection string |
| `AZURE_STORAGE_CONTAINER` | Container name (optional, default: bug-analytics-uploads) |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |

## 📚 Full Documentation

See [STREAMLIT_DEPLOYMENT.md](../STREAMLIT_DEPLOYMENT.md) for:
- Architecture overview
- Deployment to Streamlit Cloud
- Troubleshooting
- Advanced configuration

## 🏗️ Architecture

The UI is cleanly separated from business logic:

```
qa_bugs/services/         ← Core analysis (shared with CLI)
qa_bugs_cli/              ← CLI interface (HTML reports)
qa_bugs_ui/               ← Streamlit interface (THIS)
```

Both CLI and UI use the same `AnalysisService` - same metrics, same results!

## 🆘 Support

- Check [STREAMLIT_DEPLOYMENT.md](../STREAMLIT_DEPLOYMENT.md)
- Review main [README.md](../README.md)
- Streamlit docs: https://docs.streamlit.io
