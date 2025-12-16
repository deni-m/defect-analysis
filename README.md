# QA Bugs Analytics (Starter)

## Quick start
```bash
# 1) Create venv & install
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

# 2) Run on sample data (produces output/run_YYYYMMDD_HHMM/report.html)
qa-bugs run   --config configs/example.config.yml   --input data/sample_bugs.csv   --since 2025-09-01 --until 2025-09-30   --metrics defect_age,age_by_priority   --llm off
```

Open the generated `report.html` in a browser.

## Exporting data from Jira

You can pull fresh issues directly from Jira into a CSV compatible with the analytics pipeline.

### 1. Configure environment
Copy `.env.example` to `.env` and fill (provide full JQL in `JIRA_JQL_EXTRA` including project clause):
```
JIRA_URL=https://your-domain.atlassian.net
JIRA_USER=your-email@example.com
JIRA_TOKEN=your_api_token
JIRA_JQL_EXTRA=project=PROJECTKEY AND status != Done AND priority in (High, Critical)
```
Generate an API token from Atlassian account security settings.

### 2. Install dependencies (if not already)
`pip install -e .` will install `requests` used by the exporter.

### 3. Run exporter
```bash
python -m qa_bugs.automation.jira_export export --output data/jira_issues.csv --limit 100
```
Filtering now uses an env var `JIRA_JQL_EXTRA` (required, full JQL). Example in `.env.example` already includes the `project=` clause.
Adjust batch size or limit:
- `--batch-size 500` (Jira caps at 1000)
- `--limit 1000`

### 4. Generate report on exported data
```bash
qa-bugs --config configs/example.config.yml --input data/jira_issues.csv --llm off
```

The CSV headers will match the configured `fields_mapping` (e.g., `Created`, `Resolved`, `FixVersion`).

## Testing

Unit tests use `pytest`.

Run the full suite (excluding optional live tests by default):

```bash
python -m pytest
```

Run a single test file:

```bash
python -m pytest tests/test_defect_age.py -q
```

### Live LLM test

`tests/test_llm_live.py` is marked with `@pytest.mark.live` and performs a real Azure OpenAI request.
It is skipped unless the following environment variables are set:

* `AZURE_OPENAI_KEY`
* `AZURE_OPENAI_ENDPOINT`
* (optional) `AZURE_OPENAI_DEPLOYMENT` (defaults to `gpt-4o`)
* (optional) `AZURE_OPENAI_API_VERSION` (defaults to `2024-05-01-preview`)

Run only live tests:

```bash
python -m pytest -m live
```

Exclude live tests:

```bash
python -m pytest -m "not live"
```

### Adding tests

Place new test files in `tests/` named `test_*.py`. Keep each test focused with minimal assertions covering:
1. Happy path
2. One edge case (e.g., empty dataframe)
3. One configuration variance

## Debugging & Logging

### Log Files

**Automatic file logging is now enabled by default:**

**CLI runs:**
- Logs saved to: `output/run_YYYYMMDD_HHMM/qa_bugs.log`
- Includes all field mapping, analysis, and LLM activity
- DEBUG level details in file, INFO level in console

**UI runs:**
- Field mapping: `output/ui_session_YYYYMMDD_HHMMSS/qa_bugs_ui.log`
- Analysis: `output/ui_run_YYYYMMDD_HHMMSS/qa_bugs_ui.log`
- Includes all activity at DEBUG level

**LLM prompt/response files (when `log_prompts: true`):**
- Saved in same output directory as logs
- Format: `prompt_{metric_id}_{timestamp}.txt` and `response_{metric_id}_{timestamp}.txt`

### Enabling Detailed Logs in Code

For scripts or notebooks, configure logging manually:

```python
import logging

# For detailed debugging (includes fuzzy match scores, LLM responses)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# For high-level progress tracking
logging.basicConfig(level=logging.INFO)
```

### Key Log Messages

**Field Mapping Detection:**
- `Auto-detecting field mapping for N columns` - Detection starting
- `LLM service is enabled` or `using fuzzy matching only` - Detection method selected
- `LLM prompt:` / `LLM response:` - DEBUG level shows full LLM interaction
- `Fuzzy match: 'key' -> 'Issue ID' (score: 0.75)` - DEBUG level match scores
- `LLM detection successful` or `Falling back to fuzzy matching` - Result status
- `validation: valid=True, errors=0, warnings=2` - Validation summary

**When to Use:**
- Debugging why certain CSV columns aren't detected
- Understanding LLM vs fuzzy matching decisions
- Reviewing actual LLM prompts and responses for troubleshooting
- Troubleshooting missing required fields
- Analyzing low similarity scores in fuzzy matching

See `demo_field_mapper_logging.py` for a working example.

## Documentation

- **Auto Field Mapping**: See [docs/AUTO_MAPPING.md](docs/AUTO_MAPPING.md) for detailed guide on automatic CSV field detection
- **Streamlit Deployment**: See [STREAMLIT_DEPLOYMENT.md](STREAMLIT_DEPLOYMENT.md) for UI deployment instructions
