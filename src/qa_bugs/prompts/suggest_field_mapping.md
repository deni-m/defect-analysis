# Field Mapping Auto-Detection Prompt

You are a data mapping assistant. Given CSV column headers and sample data, suggest which columns map to our canonical field names.

**Canonical fields (REQUIRED - must be mapped):**
- key: unique bug/defect identifier (e.g., JIRA-123)
- created_at: timestamp when bug was created
- status: current bug state (e.g., Open, Closed, Resolved)
- priority: bug priority level (e.g., High, Medium, Low)

**Canonical fields (OPTIONAL - map if available):**
- resolved_at: timestamp when bug was resolved/closed
- environment: deployment environment (DEV, QA, PROD, etc.)
- category: bug category or type
- fix_version: target fix version or release

**Task:**
Analyze the provided CSV columns and sample rows. Return ONLY valid YAML mapping in this exact format:

```yaml
fields_mapping:
  key: <column_name>
  created_at: <column_name>
  status: <column_name>
  priority: <column_name>
  resolved_at: <column_name>  # omit if not found
  environment: <column_name>  # omit if not found
  category: <column_name>  # omit if not found
  fix_version: <column_name>  # omit if not found
```

**Rules:**
- ALL REQUIRED fields (key, created_at, status, priority) MUST be mapped
- Only include mappings you're confident about (>80% certainty)
- Use exact column names from the CSV (case-sensitive)
- If a canonical field has no clear match, omit it from the output
- Return ONLY the YAML block, no explanation or markdown fences

**CSV Data:**
{{csv_sample}}

Your response (YAML only):
