# Auto Field Mapping Feature

## Overview

The auto field mapping feature uses AI (LLM) to automatically detect and map CSV column names to canonical field names, eliminating the need for manual configuration in most cases.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Entry Points (CLI/UI)                     │
├─────────────────────────────────────────────────────────────┤
│  CLI: --auto-map flag                                        │
│  UI:  Toggle "Auto-detect fields" in sidebar                │
│  Config: auto_mapping.enabled = true                         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│           FieldMappingService (field_mapper.py)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ if LLM enabled:                                       │  │
│  │   1. Analyze CSV headers + sample data with LLM      │  │
│  │   2. Parse YAML response                              │  │
│  │ else:                                                  │  │
│  │   1. Use fuzzy string matching with synonyms         │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                 Validation Layer                             │
│  • Check all REQUIRED fields present: key, created_at,      │
│    status, priority                                          │
│  • Check mapped columns exist in CSV                         │
│  • Return: ValidationResult(valid, mapping, errors)         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼ (if valid)
┌─────────────────────────────────────────────────────────────┐
│        Analysis proceeds with detected mapping               │
└─────────────────────────────────────────────────────────────┘
```

## Required vs Optional Fields

### Required Fields (MUST be mapped)
- `key` - Unique bug/defect identifier
- `created_at` - Timestamp when bug was created
- `status` - Current bug state
- `priority` - Bug priority level

### Optional Fields (enhance analysis)
- `resolved_at` - Timestamp when bug was resolved/closed
- `environment` - Deployment environment (DEV, QA, PROD, etc.)
- `category` - Bug category or type
- `fix_version` - Target fix version or release

## Usage

### Via CLI

```bash
# Enable auto-mapping for one run
qa-bugs run --config configs/example.config.yml \
  --input data/bugs.csv \
  --auto-map

# With other options
qa-bugs run --config configs/example.config.yml \
  --input data/bugs.csv \
  --auto-map \
  --since 2024-01-01 \
  --until 2024-12-31 \
  --llm on
```

### Via Streamlit UI

1. Launch UI: `streamlit run qa_bugs_ui/app.py`
2. In sidebar, check **"Auto-detect fields"**
3. Upload CSV file
4. Review detected mapping before analysis
5. Analysis proceeds only if all required fields found

### Via Config File

```yaml
# configs/example.config.yml

auto_mapping:
  enabled: true      # Enable by default
  sample_rows: 5     # Number of rows to analyze
```

## How It Works

### 1. LLM-Based Detection (Primary)

When LLM is enabled and configured:

1. **Sample Analysis**: Reads first N rows (configurable via `sample_rows`)
2. **Prompt Construction**: Builds prompt with:
   - CSV column names
   - Sample data rows
   - Required/optional field definitions
3. **LLM Call**: Sends to Azure OpenAI (gpt-4o-mini recommended)
4. **YAML Parsing**: Extracts field mapping from response
5. **Validation**: Ensures all required fields present

**Prompt Template**: See `qa_bugs/prompts/suggest_field_mapping.md`

### 2. Fuzzy Matching Fallback

If LLM unavailable or fails:

1. **String Similarity**: Uses `difflib.SequenceMatcher`
2. **Synonym Matching**: Compares against known synonyms:
   - `key`: ["id", "bug_id", "defect_id", "issue_id", "key", "ticket"]
   - `created_at`: ["created", "created_at", "creation_date", "opened"]
   - `status`: ["status", "state", "resolution"]
   - etc.
3. **Threshold**: 0.6 minimum similarity score
4. **Best Match**: Picks highest scoring column for each field

## Logging & Debugging

The field mapper includes comprehensive logging to help understand the detection process:

### Enabling Logging

```python
import logging

# Set log level to DEBUG to see detailed matching scores
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Or just INFO for high-level steps
logging.basicConfig(level=logging.INFO)
```

### Log Messages

**INFO Level** - Key decision points:
```
Auto-detecting field mapping for 6 columns, 3 rows
LLM service is available, attempting LLM-based detection
LLM detection successful, parsed 7 field mappings
Starting fuzzy matching detection
Fuzzy matching completed, detected 7 field mappings
LLM mapping validation: valid=True, errors=0, warnings=2
```

**DEBUG Level** - Detailed scores and process:
```
LLM prompt:
You are a data mapping assistant...
[full prompt with CSV sample]

Sending prompt to LLM (length: 1595 chars)
LLM call successful, parsing response
LLM response:
fields_mapping:
  key: IssueKey
  created_at: CreatedDate
  status: Status
  priority: Priority

Fuzzy match: key -> IssueKey (score: 0.75)
Fuzzy match: created_at -> Created (score: 0.83)
Fuzzy match: status -> Bug Status (score: 0.67)
```

**WARNING Level** - Fallback scenarios:
```
LLM detection failed: Invalid YAML response
Falling back to fuzzy matching
No match found for optional field 'environment'
```

**ERROR Level** - Critical failures:
```
LLM service error during field mapping: [error details]
Fuzzy matching failed: No suitable matches found
```

### Practical Debugging Example

```python
import logging
from qa_bugs.ingest.field_mapper import FieldMappingService
from qa_bugs.llm.service import LLMService

# Enable detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(name)s - %(levelname)s - %(message)s'
)

# Create service
llm_service = LLMService() if llm_enabled else None
mapper = FieldMappingService(llm_service=llm_service)

# Auto-detect with logging enabled
result = mapper.auto_detect_mapping(df, sample_rows=5)

# Log output shows:
# qa_bugs.ingest.field_mapper - INFO - Auto-detecting field mapping for 10 columns, 3 rows
# qa_bugs.ingest.field_mapper - INFO - LLM service not available, using fuzzy matching only
# qa_bugs.ingest.field_mapper - DEBUG - Fuzzy match for 'key': 'Issue Key' (score: 0.80)
# qa_bugs.ingest.field_mapper - DEBUG - Fuzzy match for 'status': 'Status' (score: 1.00)
# ...
```

### What to Look For

**When debugging detection issues:**
- Check if "LLM service is available" or "using fuzzy matching only" appears
- Review DEBUG fuzzy match scores - low scores (<0.65) may indicate poor matches
- Look for WARNING messages about missing required fields
- Check validation results: "errors=0" means all required fields found

**Common patterns:**
- `LLM service not available` → Check Azure OpenAI credentials
- `score: 0.45` (low score) → Column name doesn't match expected patterns
- `No match found for` → Optional field missing, analysis continues
- `Falling back to fuzzy matching` → LLM failed, using backup method

### 3. Validation

After detection (LLM or fuzzy), validation checks:

✅ **Pass Criteria:**
- All required fields mapped
- All mapped columns exist in CSV
- No critical errors

❌ **Fail Criteria:**
- Missing required fields → Analysis blocked
- Mapped columns don't exist → Error shown
- Invalid YAML from LLM → Falls back to fuzzy

⚠️ **Warnings (non-blocking):**
- Missing optional fields
- Duplicate column mappings
- LLM detection failed (using fuzzy fallback)

## Error Messages

### Missing Required Fields

```
❌ Field Mapping Validation Failed

**Errors:**
  • Required field 'status' not mapped
  • Required field 'priority' not mapped

**Missing Required Fields:**
  status, priority

**Action Required:**
  1. Check your CSV file has these columns
  2. Or manually configure field mapping in config file
  3. Or fix field names in your CSV export
```

### Column Not Found

```
❌ Field Mapping Validation Failed

**Errors:**
  • Mapped column 'BugStatus' for field 'status' does not exist in CSV

**Action Required:**
  1. Verify column names in CSV match exactly
  2. Check for typos or case sensitivity
```

## Configuration

### Full Config Example

```yaml
# configs/example.config.yml

project:
  timezone: "UTC"

# Manual mapping (used if auto_mapping disabled)
fields_mapping:
  key: "Issue Key"
  created_at: "Created Date"
  status: "Status"
  priority: "Priority"
  resolved_at: "Resolved Date"
  environment: "Environment"

# Auto-mapping configuration
auto_mapping:
  enabled: false     # Set to true to enable
  sample_rows: 5     # Rows to analyze (1-10 recommended)

# LLM must be enabled for AI-based detection
llm:
  enabled: true
  provider: azure
  endpoint: "https://your-endpoint.openai.azure.com"
  deployment: "gpt-4o-mini"
  api_version: "2024-05-01-preview"
```

## Behavioral Rules

### Priority Hierarchy

1. **CLI flag** `--auto-map` → Overrides config
2. **UI toggle** → Overrides config
3. **Config** `auto_mapping.enabled` → Default behavior
4. **Manual mapping** `fields_mapping` → Used if auto disabled

### LLM Requirements

Auto-mapping with LLM requires:
- `llm.enabled: true` in config
- Environment variables set:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_KEY`
- Valid Azure OpenAI deployment

If requirements not met → Falls back to fuzzy matching

### Backwards Compatibility

✅ **Fully backwards compatible:**
- Default: `auto_mapping.enabled: false`
- Existing configs work without changes
- Manual `fields_mapping` still fully supported
- No breaking changes to existing flows

## Testing

### Unit Tests

```bash
# Run field mapper tests
python tests/test_field_mapper.py

# Or with pytest
pytest tests/test_field_mapper.py -v
```

### Manual Testing

**Test Case 1: Exact Match**
```python
df = pd.DataFrame({
    "key": ["BUG-1"],
    "created_at": ["2024-01-01"],
    "status": ["Open"],
    "priority": ["High"]
})
# Expected: Auto-detected perfectly
```

**Test Case 2: Similar Names**
```python
df = pd.DataFrame({
    "Issue Key": ["BUG-1"],
    "Created Date": ["2024-01-01"],
    "Issue Status": ["Open"],
    "Bug Priority": ["High"]
})
# Expected: Fuzzy matching succeeds
```

**Test Case 3: Custom Names**
```python
df = pd.DataFrame({
    "ticket_id": ["BUG-1"],
    "opened_date": ["2024-01-01"],
    "current_state": ["Open"],
    "severity": ["High"]
})
# Expected: LLM detects, fuzzy might partially fail
```

**Test Case 4: Missing Required**
```python
df = pd.DataFrame({
    "key": ["BUG-1"],
    "created_at": ["2024-01-01"]
    # Missing status and priority
})
# Expected: Validation fails, clear error message
```

## Performance

### LLM-Based Detection
- **Latency**: ~2-5 seconds per CSV
- **Cost**: ~$0.001 per detection (gpt-4o-mini)
- **Accuracy**: ~95% for standard JIRA exports

### Fuzzy Matching
- **Latency**: <100ms per CSV
- **Cost**: Free
- **Accuracy**: ~70% for standard JIRA exports

## Troubleshooting

### LLM Not Working

**Symptoms:**
- Falls back to fuzzy matching immediately
- Warning: "LLM detection failed"

**Solutions:**
1. Check environment variables:
   ```bash
   echo $env:AZURE_OPENAI_ENDPOINT
   echo $env:AZURE_OPENAI_KEY
   ```
2. Verify LLM config in YAML
3. Test LLM separately: `python tests/check_llm.py`

### Incorrect Mappings

**Symptoms:**
- Fields mapped to wrong columns
- Validation passes but analysis fails

**Solutions:**
1. Review detected mapping before accepting
2. Increase `sample_rows` (more context for LLM)
3. Use manual mapping for unusual column names
4. Check CSV for duplicate/ambiguous headers

### Validation Always Fails

**Symptoms:**
- "Required field not mapped" for every run
- Even with correct column names

**Solutions:**
1. Check CSV column names (case-sensitive)
2. Look for leading/trailing spaces in headers
3. Ensure CSV is properly formatted
4. Try manual mapping first to isolate issue

## Implementation Details

### Key Files

- **`qa_bugs/ingest/field_mapper.py`** - Core service
- **`qa_bugs/services/models.py`** - Config models
- **`qa_bugs_cli/cli.py`** - CLI integration
- **`qa_bugs_ui/app.py`** - Streamlit UI integration
- **`qa_bugs/prompts/suggest_field_mapping.md`** - LLM prompt
- **`tests/test_field_mapper.py`** - Unit tests

### Extension Points

To add new canonical fields:

1. Update `FieldMappingService.REQUIRED_FIELDS` or `OPTIONAL_FIELDS`
2. Add synonyms to `FIELD_SYNONYMS` dict
3. Update LLM prompt in `_build_mapping_prompt()`
4. Update `Normalizer` to handle new field

## Future Enhancements

- [ ] Support for confidence scores per mapping
- [ ] Interactive correction in UI (edit detected mapping)
- [ ] Learning from user corrections
- [ ] Support for non-JIRA CSV formats
- [ ] Batch CSV processing with caching
- [ ] Export detected mapping to config file
- [ ] Multi-language support for column names
