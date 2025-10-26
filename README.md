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
