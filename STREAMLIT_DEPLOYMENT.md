# Streamlit UI Deployment Guide

This guide explains how to deploy and run the QA Bugs Analytics Streamlit web UI.

## 🏗️ Architecture

The application has been refactored with clean separation:

```
bug-analytics/
├── qa_bugs/              # Core business logic (UI-agnostic)
│   ├── core/
│   ├── ingest/
│   ├── metrics/
│   ├── llm/
│   └── services/        # NEW: Service layer
│       ├── models.py           # AnalysisConfig, AnalysisResult
│       ├── analysis_service.py # Main orchestration
│       └── storage_service.py  # Azure Blob Storage
├── qa_bugs_cli/         # CLI interface (HTML reports)
│   ├── cli.py
│   └── html_report.py
└── qa_bugs_ui/          # Streamlit web interface
    ├── app.py                  # Main Streamlit app
    ├── config/
    │   └── default.yml         # Analysis configuration
    └── components/
        └── results_display.py  # UI components
```

## 🚀 Running Locally

### 1. Install Dependencies

```bash
# Install package with all dependencies
pip install -e .

# Or install from requirements
pip install streamlit azure-storage-blob python-dotenv
```

### 2. Configure Secrets

Create `.streamlit/secrets.toml` from the example:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` with your Azure credentials:

```toml
AZURE_STORAGE_CONNECTION_STRING = "your_actual_connection_string"
AZURE_STORAGE_CONTAINER = "bug-analytics-uploads"

AZURE_OPENAI_API_KEY = "your_actual_key"
AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
```

**Important:** Never commit `secrets.toml` to git!

### 3. Run Streamlit

```bash
streamlit run qa_bugs_ui/app.py
```

The app will open in your browser at `http://localhost:8501`

## ☁️ Deploying to Streamlit Cloud

### 1. Push to GitHub

Ensure your code is in a GitHub repository.

### 2. Connect to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select your repository
5. Set main file path: `qa_bugs_ui/app.py`
6. Click "Deploy"

### 3. Configure Secrets in Streamlit Cloud

1. In your app settings, click "Secrets"
2. Add your secrets in TOML format:

```toml
AZURE_STORAGE_CONNECTION_STRING = "your_connection_string"
AZURE_STORAGE_CONTAINER = "bug-analytics-uploads"

AZURE_OPENAI_API_KEY = "your_key"
AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
AZURE_OPENAI_API_VERSION = "2024-05-01-preview"
AZURE_OPENAI_DEPLOYMENT = "gpt-4o-mini"
```

3. Click "Save"

### 4. App will redeploy automatically

## 🔧 Configuration

### Analysis Configuration

The default analysis configuration is in `qa_bugs_ui/config/default.yml`:

```yaml
project:
  timezone: "Europe/Kyiv"

fields_mapping:
  key: "Key"
  created_at: "Created"
  resolved_at: "resolutiondate"
  status: "Status"
  priority: "Priority"
  # ... more mappings

metrics:
  enabled:
    - leakage_rate
    - defects_by_env_priority
    - cumulative_open_closed
    - status_by_severity
    - defect_age
    - age_by_priority
    - rejection_rate

llm:
  enabled: true
  deployment: "gpt-4o-mini"
  # ... more LLM settings
```

### Customizing for Your JIRA Instance

Edit `qa_bugs_ui/config/default.yml` to match your JIRA field names:

1. Update `fields_mapping` to match your CSV column names
2. Adjust `metric_params` for your environment names
3. Configure `llm` settings for your Azure OpenAI deployment

## 🎯 Usage Workflow

1. **Upload CSV**: User uploads JIRA CSV export via web UI
2. **Azure Storage**: File is automatically saved to Azure Blob Storage
3. **Analysis**: Service layer processes the data using configured metrics
4. **LLM Insights**: Azure OpenAI generates insights (if enabled)
5. **Display**: Results shown inline with interactive Plotly charts

## 🔐 Environment Variables

The app supports both Streamlit secrets and environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Yes | Azure Storage connection string |
| `AZURE_STORAGE_CONTAINER` | No | Container name (default: bug-analytics-uploads) |
| `AZURE_OPENAI_API_KEY` | Yes* | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Yes* | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_VERSION` | No | API version (default from config) |
| `AZURE_OPENAI_DEPLOYMENT` | No | Deployment name (default from config) |

*Required if LLM insights are enabled

## 📊 Features

- ✅ File upload (CSV)
- ✅ Azure Blob Storage integration
- ✅ All 7 metrics computed
- ✅ AI-powered insights via Azure OpenAI
- ✅ Interactive Plotly visualizations
- ✅ Optional date range filters
- ✅ Data preview
- ✅ Expandable metric sections
- ❌ No session persistence (results cleared on refresh)
- ❌ No metric configuration UI (uses default config)

## 🐛 Troubleshooting

### "Azure Storage connection string not found"

- Ensure `AZURE_STORAGE_CONNECTION_STRING` is set in `.streamlit/secrets.toml` (local) or Streamlit Cloud secrets
- Check that the connection string is valid

### "Module not found" errors

- Run `pip install -e .` from the project root
- Ensure all dependencies are installed

### Plotly charts not rendering

- Check browser console for JavaScript errors
- Ensure CDN is accessible: `https://cdn.plot.ly/plotly-2.30.0.min.js`

### LLM insights failing

- Verify `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` are correct
- Check Azure OpenAI deployment name matches config
- Review logs for API errors

### "TypeError: 'list' object cannot be interpreted as an integer"

- This can occur if a Streamlit `expander` gets a non-boolean `expanded` value.
- Pull the latest UI fixes and restart the Streamlit app.

## 🔄 Upgrading from CLI

The CLI still works! Both interfaces use the same service layer:

```bash
# CLI (generates HTML report)
qa-bugs run --config configs/example.config.yml --input data/sample.csv

# Streamlit (web UI)
streamlit run qa_bugs_ui/app.py
```

## 📝 Next Steps

Possible enhancements:

- [ ] Add metric configuration UI
- [ ] Support multiple file comparison
- [ ] Add report export (PDF/HTML download)
- [ ] Implement user authentication
- [ ] Add report history/persistence
- [ ] Direct JIRA integration (no CSV needed)
- [ ] Custom metric builder

## 🆘 Support

For issues or questions:
- Check the main [README.md](README.md)
- Review code comments in `qa_bugs_ui/app.py`
- Check Streamlit docs: https://docs.streamlit.io
