"""Integration test for field mapping with real LLM calls."""
import os
import pytest
import pandas as pd
from qa_bugs.ingest.field_mapper import FieldMappingService
from qa_bugs.llm.service import LLMService


@pytest.fixture
def llm_service():
    """Create LLMService instance from environment."""
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_KEY")
    
    if not endpoint or not api_key:
        pytest.skip("Azure OpenAI credentials not configured")
    
    llm_config = {
        "enabled": True,
        "prompts_dir": "qa_bugs/prompts",
        "provider": "azure",
        "endpoint": endpoint,
        "deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        "api_version": "2024-05-01-preview",
        "temperature": 0.1,
        "max_tokens": 1000,
        "debug": False,
    }
    
    return LLMService(llm_config)


def test_llm_standard_jira_export(llm_service):
    """Test LLM with standard JIRA CSV export format."""
    df = pd.DataFrame({
        "Issue key": ["PROJ-123", "PROJ-124", "PROJ-125"],
        "Summary": ["Bug in login", "Crash on startup", "UI rendering issue"],
        "Created": ["2024-01-01 10:00", "2024-01-02 11:30", "2024-01-03 14:15"],
        "Status": ["Open", "In Progress", "Resolved"],
        "Priority": ["High", "Critical", "Medium"],
        "Resolution date": ["", "", "2024-01-10 16:00"],
        "Environment": ["QA", "PROD", "DEV"],
        "Issue Type": ["Bug", "Bug", "Bug"],
        "Fix Version/s": ["1.2.0", "1.1.1", "1.2.0"]
    })
    
    mapper = FieldMappingService(llm_service=llm_service)
    result = mapper.auto_detect_mapping(df, sample_rows=3)
    
    print("\n=== LLM Detection: Standard JIRA ===")
    print(f"Valid: {result.valid}")
    print(f"Mapping: {result.mapping}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    
    # Assertions
    assert result.valid, f"Mapping should be valid. Errors: {result.errors}"
    assert "key" in result.mapping, "key field should be mapped"
    assert "created_at" in result.mapping, "created_at field should be mapped"
    assert "status" in result.mapping, "status field should be mapped"
    assert "priority" in result.mapping, "priority field should be mapped"
    
    # Check that LLM picked correct columns
    assert result.mapping["key"].lower() == "issue key"
    assert result.mapping["status"].lower() == "status"
    assert result.mapping["priority"].lower() == "priority"


def test_llm_custom_column_names(llm_service):
    """Test LLM with non-standard column names."""
    df = pd.DataFrame({
        "Ticket ID": ["BUG-001", "BUG-002"],
        "Title": ["Cannot save file", "App freezes"],
        "Opened On": ["2024-01-01", "2024-01-02"],
        "Current State": ["New", "Assigned"],
        "Severity Level": ["P1", "P2"],
        "Closed On": ["", "2024-01-05"],
        "Test Environment": ["QA", "STAGE"]
    })
    
    mapper = FieldMappingService(llm_service=llm_service)
    result = mapper.auto_detect_mapping(df, sample_rows=2)
    
    print("\n=== LLM Detection: Custom Names ===")
    print(f"Valid: {result.valid}")
    print(f"Mapping: {result.mapping}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    
    # Assertions
    assert result.valid, f"Mapping should be valid. Errors: {result.errors}"
    
    # Check semantic understanding (LLM should map these correctly)
    assert "ticket id" in result.mapping["key"].lower() or "ticket" in result.mapping["key"].lower()
    assert "opened" in result.mapping["created_at"].lower() or "opened on" in result.mapping["created_at"].lower()
    assert "state" in result.mapping["status"].lower() or "current state" in result.mapping["status"].lower()
    assert "severity" in result.mapping["priority"].lower() or "level" in result.mapping["priority"].lower()


def test_llm_missing_required_fields(llm_service):
    """Test LLM behavior when required fields are missing."""
    df = pd.DataFrame({
        "Bug ID": ["001", "002"],
        "Description": ["Issue A", "Issue B"],
        "Date": ["2024-01-01", "2024-01-02"]
        # Missing: status, priority (required fields)
    })
    
    mapper = FieldMappingService(llm_service=llm_service)
    result = mapper.auto_detect_mapping(df, sample_rows=2)
    
    print("\n=== LLM Detection: Missing Fields ===")
    print(f"Valid: {result.valid}")
    print(f"Mapping: {result.mapping}")
    print(f"Missing Required: {result.missing_required}")
    print(f"Errors: {result.errors}")
    
    # Assertions
    assert not result.valid, "Mapping should be invalid due to missing required fields"
    assert "status" in result.missing_required, "status should be in missing required"
    assert "priority" in result.missing_required, "priority should be in missing required"
    assert len(result.errors) > 0, "Should have validation errors"


def test_llm_ambiguous_columns(llm_service):
    """Test LLM with ambiguous/duplicate column names."""
    df = pd.DataFrame({
        "ID": ["001", "002"],
        "Key": ["BUG-001", "BUG-002"],
        "Created": ["2024-01-01", "2024-01-02"],
        "Status": ["Open", "Closed"],
        "Priority": ["High", "Low"],
        "Priority Level": ["P1", "P2"]  # Duplicate semantic meaning
    })
    
    mapper = FieldMappingService(llm_service=llm_service)
    result = mapper.auto_detect_mapping(df, sample_rows=2)
    
    print("\n=== LLM Detection: Ambiguous Columns ===")
    print(f"Valid: {result.valid}")
    print(f"Mapping: {result.mapping}")
    print(f"Warnings: {result.warnings}")
    
    # Should still be valid, but might pick one of the ambiguous columns
    assert result.valid, "Should handle ambiguous columns and still be valid"
    assert "key" in result.mapping
    assert "priority" in result.mapping


def test_llm_with_jira_custom_fields(llm_service):
    """Test LLM with JIRA custom field format (customfield_XXXXX)."""
    df = pd.DataFrame({
        "Issue key": ["PROJ-1", "PROJ-2"],
        "Summary": ["Bug 1", "Bug 2"],
        "Created": ["2024-01-01", "2024-01-02"],
        "Status": ["Open", "Closed"],
        "Priority": ["High", "Medium"],
        "customfield_12200": ["QA", "PROD"],  # Environment custom field
        "customfield_10500": ["1.0", "1.1"]   # Version custom field
    })
    
    mapper = FieldMappingService(llm_service=llm_service)
    result = mapper.auto_detect_mapping(df, sample_rows=2)
    
    print("\n=== LLM Detection: JIRA Custom Fields ===")
    print(f"Valid: {result.valid}")
    print(f"Mapping: {result.mapping}")
    print(f"Warnings: {result.warnings}")
    
    # Should detect required fields correctly
    assert result.valid
    assert result.mapping["key"].lower() == "issue key"
    
    # LLM should ideally detect custom fields by analyzing data patterns
    # (QA/PROD suggests environment, version numbers suggest fix_version)


@pytest.mark.parametrize("sample_rows", [1, 3, 5, 10])
def test_llm_different_sample_sizes(llm_service, sample_rows):
    """Test how sample size affects LLM accuracy."""
    df = pd.DataFrame({
        "Ticket": [f"T-{i:03d}" for i in range(20)],
        "Description": [f"Issue {i}" for i in range(20)],
        "Opened": [f"2024-01-{i+1:02d}" for i in range(20)],
        "State": ["Open"] * 10 + ["Closed"] * 10,
        "Severity": ["High", "Medium", "Low"] * 6 + ["High", "Low"]
    })
    
    mapper = FieldMappingService(llm_service=llm_service)
    result = mapper.auto_detect_mapping(df, sample_rows=sample_rows)
    
    print(f"\n=== LLM Detection: {sample_rows} Sample Rows ===")
    print(f"Valid: {result.valid}")
    print(f"Mapping: {result.mapping}")
    
    # All sample sizes should produce valid results for clear data
    assert result.valid, f"Should be valid with {sample_rows} rows"


def test_llm_fallback_on_failure():
    """Test that fuzzy matching kicks in if LLM fails."""
    df = pd.DataFrame({
        "IssueKey": ["B-1", "B-2"],
        "CreatedDate": ["2024-01-01", "2024-01-02"],
        "IssueStatus": ["Open", "Closed"],
        "BugPriority": ["High", "Low"]
    })
    
    # Create mapper with intentionally bad LLM service (None) to force fuzzy fallback
    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df, sample_rows=2)
    
    print("\n=== LLM Fallback Test ===")
    print(f"Valid: {result.valid}")
    print(f"Mapping: {result.mapping}")
    print(f"Warnings: {result.warnings}")
    
    # Should fall back to fuzzy matching - when llm_service is None, fuzzy is used directly
    assert result.valid, "Fuzzy matching should succeed as fallback"
    # No LLM warning expected when llm_service is None (it's disabled, not failed)


if __name__ == "__main__":
    """Run tests manually without pytest."""
    import sys
    from qa_bugs.llm.service import LLMService
    
    # Check credentials
    if not os.getenv("AZURE_OPENAI_ENDPOINT") or not os.getenv("AZURE_OPENAI_KEY"):
        print("❌ Azure OpenAI credentials not set!")
        print("\nSet these environment variables:")
        print("  AZURE_OPENAI_ENDPOINT")
        print("  AZURE_OPENAI_KEY")
        sys.exit(1)
    
    # Create LLMService instance
    config = {
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        "api_version": "2024-05-01-preview"
    }
    llm_service = LLMService(**config)
    
    print("=" * 70)
    print("Running Field Mapper LLM Integration Tests")
    print("=" * 70)
    
    try:
        print("\n[1/7] Testing standard JIRA export...")
        test_llm_standard_jira_export(llm_service)
        print("✓ PASSED")
        
        print("\n[2/7] Testing custom column names...")
        test_llm_custom_column_names(llm_service)
        print("✓ PASSED")
        
        print("\n[3/7] Testing missing required fields...")
        test_llm_missing_required_fields(llm_service)
        print("✓ PASSED")
        
        print("\n[4/7] Testing ambiguous columns...")
        test_llm_ambiguous_columns(llm_service)
        print("✓ PASSED")
        
        print("\n[5/7] Testing JIRA custom fields...")
        test_llm_with_jira_custom_fields(llm_service)
        print("✓ PASSED")
        
        print("\n[6/7] Testing different sample sizes...")
        for rows in [1, 3, 5]:
            test_llm_different_sample_sizes(llm_service, rows)
        print("✓ PASSED")
        
        print("\n[7/7] Testing LLM fallback...")
        test_llm_fallback_on_failure()
        print("✓ PASSED")
        
        print("\n" + "=" * 70)
        print("✓ All LLM integration tests PASSED!")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
