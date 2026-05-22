# Field Mapper Tests

This directory contains comprehensive tests for the field mapping functionality.

## Test Files

### 1. `test_field_mapper.py` - Unit Tests (No LLM)
Tests core logic without making external API calls:
- ✅ Fuzzy string matching
- ✅ Validation logic
- ✅ Error handling
- ✅ Edge cases
- ✅ Case sensitivity

**Run:**
```bash
# Direct execution
python tests/test_field_mapper.py

# With pytest
pytest tests/test_field_mapper.py -v

# With coverage
pytest tests/test_field_mapper.py --cov=qa_bugs.ingest.field_mapper
```

**No setup required** - runs offline.

---

### 2. `test_field_mapper_llm.py` - LLM Integration Tests
Tests real Azure OpenAI integration:
- ✅ Standard JIRA exports
- ✅ Custom column names
- ✅ Missing required fields
- ✅ Ambiguous columns
- ✅ JIRA custom fields (customfield_XXXXX)
- ✅ Different sample sizes (1, 3, 5, 10 rows)
- ✅ LLM fallback behavior

**Requires:**
```bash
# Set Azure OpenAI credentials
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com"
export AZURE_OPENAI_KEY="your-api-key"

# Optional: specify deployment name
export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"  # default
```

**Run:**
```bash
# Direct execution (with detailed output)
python tests/test_field_mapper_llm.py

# With pytest
pytest tests/test_field_mapper_llm.py -v

# Run specific test
pytest tests/test_field_mapper_llm.py::test_llm_standard_jira_export -v

# Skip if credentials not available
pytest tests/test_field_mapper_llm.py -v --maxfail=1
```

**Cost:** ~$0.001 per test run (uses gpt-4o-mini)

---

## Quick Start

### Run All Tests
```bash
# Unit tests only (fast, no credentials needed)
pytest tests/test_field_mapper.py -v

# All tests (if credentials available)
pytest tests/test_field_mapper*.py -v
```

### Run with Coverage
```bash
pytest tests/test_field_mapper*.py \
  --cov=qa_bugs.ingest.field_mapper \
  --cov-report=html \
  --cov-report=term
```

### CI/CD Integration
```yaml
# .github/workflows/test.yml
- name: Run unit tests (no LLM)
  run: pytest tests/test_field_mapper.py -v

- name: Run LLM tests (if secrets available)
  if: env.AZURE_OPENAI_KEY != ''
  run: pytest tests/test_field_mapper_llm.py -v
  env:
    AZURE_OPENAI_ENDPOINT: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    AZURE_OPENAI_KEY: ${{ secrets.AZURE_OPENAI_KEY }}
```

---

## Test Coverage

### Unit Tests (`test_field_mapper.py`)
| Test | Coverage |
|------|----------|
| Exact column name matching | ✅ |
| Fuzzy matching with synonyms | ✅ |
| Case-insensitive matching | ✅ |
| Validation of required fields | ✅ |
| Missing field detection | ✅ |
| Invalid column references | ✅ |
| Error message formatting | ✅ |

### LLM Integration Tests (`test_field_mapper_llm.py`)
| Test | Coverage |
|------|----------|
| Standard JIRA export format | ✅ |
| Custom/unusual column names | ✅ |
| Missing required fields | ✅ |
| Ambiguous/duplicate columns | ✅ |
| JIRA custom fields (customfield_*) | ✅ |
| Sample size variations (1-10 rows) | ✅ |
| LLM failure → fuzzy fallback | ✅ |

---

## Expected Outputs

### Unit Tests (Passing)
```
Running Field Mapper Unit Tests

============================================================
✓ test_exact_match
✓ test_fuzzy_mapping
✓ test_validation_valid
✓ test_validation_invalid
✓ test_case_insensitive_matching
✓ test_missing_column_in_mapping
✓ test_duplicate_column_mapping
============================================================

✓ All unit tests passed!
```

### LLM Integration Tests (Passing)
```
======================================================================
Running Field Mapper LLM Integration Tests
======================================================================

[1/7] Testing standard JIRA export...

=== LLM Detection: Standard JIRA ===
Valid: True
Mapping: {'key': 'Issue key', 'created_at': 'Created', ...}
✓ PASSED

[2/7] Testing custom column names...
✓ PASSED

...

======================================================================
✓ All LLM integration tests PASSED!
======================================================================
```

---

## Troubleshooting

### Unit Tests Fail
**Issue:** `ModuleNotFoundError: No module named 'qa_bugs'`

**Solution:**
```bash
# Option 1: Set PYTHONPATH
export PYTHONPATH="$(pwd)"
python tests/test_field_mapper.py

# Option 2: Install package in editable mode
pip install -e .
pytest tests/test_field_mapper.py
```

### LLM Tests Skipped
**Issue:** `SKIPPED [1] tests/test_field_mapper_llm.py:12: Azure OpenAI credentials not configured`

**Solution:**
```bash
# Set required environment variables
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com"
export AZURE_OPENAI_KEY="your-api-key"

# Verify they're set
echo $AZURE_OPENAI_ENDPOINT
echo $AZURE_OPENAI_KEY
```

### LLM Tests Fail with 401/403
**Issue:** Authentication error from Azure OpenAI

**Solutions:**
1. Verify API key is correct
2. Check endpoint URL format (should include https://)
3. Ensure deployment name matches your Azure resource
4. Check Azure OpenAI resource has proper permissions

### LLM Tests Slow
**Issue:** Tests take >30 seconds

**Normal** - LLM tests make real API calls. Expected latency:
- ~2-5 seconds per test
- ~30-60 seconds for full suite

**To speed up:**
```bash
# Run in parallel (if pytest-xdist installed)
pytest tests/test_field_mapper_llm.py -n 3

# Run specific tests only
pytest tests/test_field_mapper_llm.py::test_llm_standard_jira_export
```

---

## Adding New Tests

### Unit Test Template
```python
def test_your_feature():
    """Test description."""
    df = pd.DataFrame({
        "Column": ["value"]
    })
    
    mapper = FieldMappingService(llm_enabled=False)
    result = mapper.auto_detect_mapping(df)
    
    assert result.valid
    assert result.mapping["key"] == "expected_column"
```

### LLM Test Template
```python
def test_llm_your_scenario(llm_config):
    """Test description."""
    df = pd.DataFrame({
        "Column": ["value"]
    })
    
    mapper = FieldMappingService(llm_enabled=True, llm_config=llm_config)
    result = mapper.auto_detect_mapping(df, sample_rows=3)
    
    assert result.valid
    assert "key" in result.mapping
```

---

## Continuous Integration

### Pre-commit Hook
```bash
# .git/hooks/pre-commit
#!/bin/bash
pytest tests/test_field_mapper.py -v || exit 1
```

### GitHub Actions
```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-cov
      
      - name: Run unit tests
        run: pytest tests/test_field_mapper.py -v --cov
      
      - name: Run LLM tests
        if: env.AZURE_OPENAI_KEY
        env:
          AZURE_OPENAI_ENDPOINT: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
          AZURE_OPENAI_KEY: ${{ secrets.AZURE_OPENAI_KEY }}
        run: pytest tests/test_field_mapper_llm.py -v
```

---

## Performance Benchmarks

### Unit Tests
- **Execution time:** <1 second
- **Cost:** $0 (offline)
- **Coverage:** ~80% of field_mapper.py

### LLM Integration Tests
- **Execution time:** 30-60 seconds (7 tests)
- **Cost:** ~$0.007 per run (with gpt-4o-mini)
- **Coverage:** 100% of LLM code paths

---

## See Also
- [AUTO_MAPPING.md](../docs/AUTO_MAPPING.md) - Feature documentation
- [README.md](../README.md) - Project overview
- `qa_bugs/ingest/field_mapper.py` - Implementation
