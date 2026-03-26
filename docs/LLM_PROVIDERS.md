# LLM Provider Configuration

The QA Bugs Analytics tool now supports both **Azure OpenAI** and direct **OpenAI API** as LLM providers.

## Quick Start

### Option 1: Azure OpenAI (Default)

1. Use `configs/example.config.yml` as your config template
2. Set environment variables:
   ```bash
   export AZURE_OPENAI_KEY="your-azure-key"
   export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com"
   ```
3. Config settings:
   ```yaml
   llm:
     provider: azure
     endpoint: "https://your-endpoint.openai.azure.com"
     deployment: "your-deployment-name"
     api_version: "2024-05-01-preview"
   ```

### Option 2: OpenAI API

1. Use `configs/example.openai.config.yml` as your config template
2. Set environment variable:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```
3. Config settings:
   ```yaml
   llm:
     provider: openai
     model: "gpt-4o-mini"  # or gpt-4o, gpt-3.5-turbo, etc.
   ```

## Configuration Parameters

### Common (Both Providers)
- `enabled`: true/false - Enable or disable LLM integration
- `provider`: "azure" or "openai" - Which provider to use
- `temperature`: 0.0-2.0 - Response randomness (some models do not support this parameter)
- `max_tokens`: integer - Max response length (default: 700)
- `enable_retries`: true/false - Retry on empty/error responses (default: false for faster fail-fast behavior)
- `debug`: true/false - Enable debug logging
- `log_prompts`: true/false - Save prompts/responses to files
- `log_raw_io`: true/false - Save raw LLM request/response JSON for each API call (stored under `llm_raw/` in run output)

### Azure-Specific
- `endpoint`: Azure OpenAI endpoint URL
- `deployment`: Azure deployment name
- `api_version`: Azure API version (e.g., "2024-05-01-preview")
- Environment: `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT`

### OpenAI-Specific
- `model`: Model name (e.g., "gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo")
- `fallback_model`: Optional backup model used when the primary model returns empty content (default: `gpt-4o-mini`)
- `api_key`: (Optional) API key - better to use environment variable
- Environment: `OPENAI_API_KEY`

## Examples

### Run with Azure OpenAI
```bash
qa-bugs run --config configs/example.config.yml --input data/sample_bugs.csv
```

### Run with OpenAI API
```bash
qa-bugs run --config configs/example.openai.config.yml --input data/sample_bugs.csv
```

### Disable LLM
```bash
qa-bugs run --config configs/example.config.yml --input data/sample_bugs.csv --llm off
```

## Switching Between Providers

To switch between Azure and OpenAI, simply:

1. **Change the config file**, or
2. **Edit the `provider` field** in your config:
   ```yaml
   llm:
     provider: openai  # Change from "azure" to "openai"
   ```
3. **Set the appropriate environment variables**

That's it! The tool will automatically use the correct API client based on your provider setting.

## Security Best Practices

- **Never commit API keys** to version control
- **Use environment variables** for credentials
- Create a `.env` file (git-ignored) for local development:
  ```bash
  # .env
  OPENAI_API_KEY=sk-...
  # or for Azure
  AZURE_OPENAI_KEY=your-key
  AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
  ```

## Troubleshooting Empty Summaries

If overall summary says there is no metric data (or appears generic), the model may be returning empty text.

- Check logs in your latest output folder for `llm_*.txt` and `qa_bugs.log`.
- Prefer stable chat models that return text consistently (for example, `gpt-4o-mini` for OpenAI).
- Ensure provider settings match your config:
   - OpenAI uses `llm.model`
   - Azure uses `llm.deployment` (or `AZURE_OPENAI_DEPLOYMENT` env var)
- If your model rejects `temperature` (for example: `Unsupported value: 'temperature'`), the app now retries automatically without `temperature`.
- If model name contains `gpt-5`, the app proactively omits `temperature` for LLM calls.
- Retries are optional. With `enable_retries: false`, the app does not run extra fallback calls and returns errors immediately.
- LLM call failures are not silently swallowed:
   - detailed errors are logged to `qa_bugs.log` (including primary/fallback failures),
   - prompt/response/error snapshots are written to `llm_*.txt` when `log_prompts: true`,
   - raw request/response/error JSON is written to `llm_raw/*.json` when `log_raw_io: true`,
   - user-facing text includes `LLM error primary=... fallback=...` when both attempts fail.
