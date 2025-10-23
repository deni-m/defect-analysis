# Bug Analytics Project

## Overview
This project is a **CLI-based analytics tool** for bug/defect data.  
It loads bug data from CSV (exported from Jira or other systems), normalizes the fields, and produces **HTML reports** with tables, charts, and optional LLM insights (via Azure OpenAI).

## Architecture
- **`qa_bugs/cli/cli.py`**  
  Typer-based CLI entrypoint. Supports options:
  - `--config` (YAML config file)
  - `--input` (CSV with bug data)
  - `--llm on|off`
  - `--since`, `--until` (optional date filters)

- **`qa_bugs/ingest/normalizer.py`**  
  Normalizes raw CSV columns into canonical fields:
  - `key`, `created_at`, `resolved_at`, `status`, `priority`, `fix_version`, `environment`, `category`

- **`qa_bugs/metrics/`**  
  Contains metric implementations:
  - `defect_age` → distribution of defect age
  - `age_by_priority` → age stats by priority
  - `cumulative_open_closed` → cumulative opened vs closed bugs
  - `leakage_rate` → defect leakage by environment and priority

- **`qa_bugs/report/builder.py`**  
  Builds the HTML report using Jinja2 + Plotly charts.

- **`qa_bugs/llm/`**  
  Integration with **Azure OpenAI** for metric insights and summary.
  - Prompts are stored under `qa_bugs/prompts/`.

## Data
Input CSV must contain:
- `Key`
- `Created [created]`
- `Resolved [resolutiondate]`
- `Status [status]`
- `Priority [priority]`
- `Fix Version/s`
- `Environment`
- `Component/s`

## Config (YAML)
Example:
```yaml
metrics:
  enabled:
    - defect_age
    - age_by_priority
    - cumulative_open_closed
    - leakage_rate
  params:
    common:
      exclude_statuses: ["Canceled", "Cancelled"]
    leakage_rate:
      intended_env: ["QA", "UAT"]
      leak_envs: ["PROD"]
