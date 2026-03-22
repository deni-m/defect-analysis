# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

QA Bugs Analytics (`qa-bugs`) — a Python tool for analyzing JIRA defect data. Produces HTML reports and optional LLM-powered insights. Two entry points: CLI and Streamlit web UI, both backed by the same `AnalysisService`.

## Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .

# Run CLI
qa-bugs run --config configs/example.config.yml --input data/bugs_sample.csv --llm off
qa-bugs run --config configs/example.config.yml --input data/bugs_sample.csv --auto-map --since 2025-09-01 --until 2025-09-30

# Run Streamlit UI
streamlit run src/qa_bugs/ui/app.py

# Tests
pytest                                    # all tests (excludes live by default)
pytest tests/test_defect_age.py -q        # single test file
pytest -m live                            # live LLM tests (needs AZURE_OPENAI_KEY + AZURE_OPENAI_ENDPOINT)
pytest -m "not live"                      # skip live tests
pytest --cov=qa_bugs --cov-report=html    # with coverage
```

No linter/formatter is configured. Follow PEP 8 and use type hints.

## Architecture

**Data flow:**
```
CSV → Normalizer (field mapping) → apply_filters (date/status)
    → [DataProfiler (optional AI classification)]
    → Metrics compute → [LLM insights (optional)]
    → HTML report / Streamlit display
```

**Key modules (all under `src/qa_bugs/`):**

- **`services/analysis_service.py`** — Main orchestrator. Runs normalization → filtering → metrics → LLM. Used by both CLI and UI.
- **`ingest/normalizer.py`** — Maps CSV columns to canonical schema (`key`, `created_at`, `resolved_at`, `status`, `priority`, `environment`, `fix_version`, `category`). All field mapping goes through here.
- **`ingest/field_mapper.py`** — Auto-detects CSV-to-canonical mappings using LLM or fuzzy matching fallback.
- **`ingest/env_value_mapper.py`** — Auto-maps environment values (e.g., "prod-server" → "PROD").
- **`metrics/base.py`** — `Metric` base class and `MetricResult` dataclass. All metrics inherit from this.
- **`metrics/__init__.py`** — `METRICS` dict registry mapping metric IDs to classes.
- **`llm/service.py`** — Wraps Azure OpenAI and direct OpenAI API. Provider selected via config `llm.provider` ("azure" or "openai").
- **`llm/prompt_manager.py`** — Loads prompt templates from `prompts/` directory; replaces `{{context_json}}` / `{{metrics_context_json}}` placeholders.
- **`services/data_profiler.py`** — AI-powered semantic classification of statuses, priorities, environments.
- **`cli/cli.py`** — Typer-based CLI entry point (`qa-bugs run`).
- **`ui/app.py`** — Streamlit UI entry point. Uses same `AnalysisService` as CLI.

## Metric Contract

Every metric **must**:
1. Inherit from `Metric` (`metrics/base.py`)
2. Implement `compute(df: pd.DataFrame, cfg: dict) -> MetricResult`
3. Return `MetricResult` with `.tables` (dict of DataFrames), `.charts` (dict of Plotly figures), `.summary` (str)
4. Validate required fields before accessing — check `if "field" not in df.columns`, return early with descriptive summary if missing
5. Register in `metrics/__init__.py` `METRICS` dict

**To add a new metric:**
1. Create `metrics/<metric_id>.py` with class inheriting `Metric`
2. Register in `metrics/__init__.py`
3. Add parameters in `configs/example.config.yml` under `metrics.params.<metric_id>`
4. Create prompt template at `prompts/metric/<metric_id>.md` (if using LLM)
5. Add tests in `tests/test_<metric_id>.py`

## Configuration

- **YAML config** (`configs/example.config.yml`): fields_mapping, auto_mapping, auto_env_mapping, auto_classification, metrics (enabled list + params), llm settings
- **Environment variables**: `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_KEY`, `JIRA_URL`, `JIRA_USER`, `JIRA_TOKEN` (see `.env.example`)
- **Streamlit secrets**: `.streamlit/secrets.toml` (git-ignored)
- All metric parameters come from `cfg` dict (from `metrics.params.<metric_id>` in YAML) — no hardcoded values
- `intended_env` and `leak_envs` config values **must be lists**, not strings

## Conventions

- Canonical field names: `key`, `created_at`, `resolved_at`, `status`, `priority`, `environment`, `fix_version`, `category`
- Timestamps coerced with `pd.to_datetime(..., errors='coerce')` — timezone handling is intentional
- Environment values are auto-uppercased by Normalizer
- Standard report column names: `age_days`, `avg_age`, `median_age`, `count`, `opened`, `closed`, `total`, `priority`, `status`, `environment`, `rate_percent`
- LLM is optional — disable with `--llm off` or `llm.enabled: false`
- Test markers: `@pytest.mark.live` for tests requiring external services (skipped if env vars missing)
- Python >=3.10 required

## Testing

Test fixtures in `tests/conftest.py` provide `sample_df` and `now_ts`. Tests are organized per-feature: `test_defect_age.py`, `test_leakage_rate.py`, `test_field_mapper.py`, `test_cli_integration.py`, `test_data_profiler.py`, etc.
