# QA Bugs Analytics (Starter)

## Quick start
```bash
# 1) Create venv & install
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

# 2) Run on sample data (produces output/run_YYYYMMDD_HHMM/report.html)
qa-bugs run   --config configs/config.yml   --input data/sample_bugs.csv   --since 2025-09-01 --until 2025-09-30   --metrics defect_age,age_by_priority   --llm off
```

Open the generated `report.html` in a browser.

## CSV Field Requirements

- Required: `key`, `created_at`, `status`, `priority`
- Optional: `resolved_at`, `environment`, `fix_version`
- Some enabled metrics may require optional fields. If missing, those metrics are skipped with warnings.

## KPI Semantics

- `Total Defects` in summary cards (CLI HTML and Streamlit UI) shows the total number of rows loaded from the input file (raw input count).
- Metric computations still apply configured filters (for example `exclude_statuses` such as `Canceled` / `Cancelled`).
- Because of this, `Total Defects` can be higher than counts used inside filtered metrics.

## Environment Handling

**Data-Driven Approach:**
- Environments are **discovered from your uploaded data**, not predefined in config
- Only environments present in the data are analyzed and displayed in reports
- Environments are ordered by defect count (most defects first) for better visibility
- If an environment doesn't exist in your data, it won't appear in any metric

**Environment Mapping:**
- Use `env_value_mapping` (manual) or `auto_env_mapping` (LLM-based) to normalize values
- Example: `"production" → "PROD"`, `"testing" → "QA"`
- Mapping happens **before** analysis, so configure `intended_env` and `leak_envs` using the **mapped values**

**Example:**
```yaml
# If your data has: "prod-server", "qa-env", "staging"
# And you map them to: PROD, QA, STAGE
# Configure leakage_rate to use mapped names:
leakage_rate:
  intended_env: ["QA", "STAGE"]  # Use mapped names
  leak_envs: ["PROD"]            # Use mapped names
```

**Warnings:**
- If you configure `intended_env` or `leak_envs` with environments not in your data, warnings will be logged
- Missing environments are skipped automatically - analysis continues with available data

## AI Data Understanding (New!)

**Automatic Classification:**
- The system can automatically classify your data semantics using AI
- No more hardcoded status lists or priority mappings
- Works with any bug tracking system (Jira, Azure DevOps, GitHub Issues, etc.)

**What Gets Classified:**
1. **Statuses** → Open / Closed / Rejected categories
2. **Priorities** → Severity order (Critical → High → Medium → Low)
3. **Environments** → Production vs Non-Production

**How to Enable:**
```yaml
# In config file:
auto_classification:
  enabled: true
  classify_statuses: true
  classify_priorities: true
  classify_environments: true
  confidence_threshold: 0.6  # Auto-apply if confidence ≥ 60%
```

Or via CLI:
```bash
qa-bugs run --config config.yml --input data.csv --auto-classify --llm on
```

**How It Works:**
1. Upload your data → AI analyzes unique status/priority values
2. LLM classification (if enabled) or fuzzy keyword matching (fallback)
3. Classifications shown in report with confidence scores
4. High-confidence classifications auto-applied to metrics
5. You can review and override AI decisions

**Benefits:**
- ✅ Works with any project (no config changes needed)
- ✅ Transparent (see what AI decided + confidence scores)
- ✅ Fallback to fuzzy matching if LLM unavailable
- ✅ Reduces config complexity
- ✅ Adapts to your project's terminology

**Report Display:**
Reports now include "� AI Data Profile" section showing:
- **Status Tab**: Open/Closed/Rejected classifications with confidence scores
- **Priority Tab**: Severity ordering from highest to lowest
- **Environment Tab**: Production vs Non-Production, pipeline order (DEV → QA → STAGE → PROD)
- **Summary Tab**: Field completeness, date range, applicable metrics
- Method used (LLM or fuzzy matching) with confidence percentage
- Any warnings or unclassified values

**Available In:**
- ✅ **CLI HTML Reports** - Detailed profile section with styling
- ✅ **Streamlit UI** - Interactive expandable tabs (Status/Priority/Environment/Summary)
- ✅ **UI Toggle** - Enable/disable auto-classification from sidebar

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
qa-bugs --config configs/config.yml --input data/jira_issues.csv --llm off
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

Run fast LLM service unit tests (no API/network calls):

```bash
python -m pytest tests/test_llm_service_unit.py -q
```

### Live LLM test

`tests/test_llm_live.py` is marked with `@pytest.mark.live` and performs a real Azure OpenAI request.
It is skipped unless the following environment variables are set:

* `AZURE_OPENAI_KEY`
* `AZURE_OPENAI_ENDPOINT`
* (optional) `AZURE_OPENAI_DEPLOYMENT` (defaults to `gpt-5.4`)
* (optional) `AZURE_OPENAI_API_VERSION` (defaults to `2024-05-01-preview`)

Run only live tests:

```bash
python -m pytest -m live
```

Exclude live tests:

```bash
python -m pytest -m "not live"
```

### E2E visual regression test (Streamlit + GPT-5-mini)

This live Playwright test starts Streamlit, uploads `data/bugs_sample.csv`, runs analysis, takes a full-page screenshot, compares it with a baseline image, and fails if GPT-5-mini reports a visual regression.

Test file:

```bash
python -m pytest tests/test_ui_e2e_visual_llm.py -q -m live
```

Install Playwright browser binaries once:

```bash
python -m playwright install chromium
```

Required for model comparison:

* `OPENAI_API_KEY` (preferred), or
* `AZURE_OPENAI_KEY` + `AZURE_OPENAI_ENDPOINT` (+ optional `AZURE_OPENAI_DEPLOYMENT`)

Baseline workflow:

1. Create/update baseline image:

```bash
$env:QA_BUGS_E2E_UPDATE_BASELINE="1"; python -m pytest tests/test_ui_e2e_visual_llm.py -q -m live
```

2. Run normal regression check:

```bash
Remove-Item Env:QA_BUGS_E2E_UPDATE_BASELINE -ErrorAction SilentlyContinue
python -m pytest tests/test_ui_e2e_visual_llm.py -q -m live
```

Artifacts:

* Baseline: `tests/baselines/ui_homepage_baseline.png`
* Current run screenshot: `tests/artifacts/ui_homepage_current.png`
* Timeout debug screenshot: `tests/artifacts/ui_analysis_timeout.png` (captured when completion markers are not detected)

Note:

* Streamlit triggers a rerun after successful analysis, so the success toast can be brief. The E2E test waits for stable result markers (for example, `Detailed Metrics` / `AI Summary`) rather than only the transient toast.

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
