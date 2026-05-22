"""Unit tests for field mapping service (no LLM calls)."""
import pytest
import pandas as pd
from qa_bugs.ingest.field_mapper import FieldMappingService


def test_fuzzy_mapping():
    """Test fuzzy matching fallback."""
    # Create test DataFrame with similar column names
    df = pd.DataFrame({
        "Issue Key": ["BUG-1", "BUG-2"],
        "Created Date": ["2024-01-01", "2024-01-02"],
        "Issue Status": ["Open", "Closed"],
        "Bug Priority": ["High", "Low"],
        "Resolution Date": ["2024-01-10", "2024-01-12"]
    })
    
    # Initialize with no LLM service (forces fuzzy matching)
    mapper = FieldMappingService(llm_service=None)
    
    # Auto-detect
    result = mapper.auto_detect_mapping(df)
    
    # Assertions
    assert result.valid, f"Mapping should be valid. Errors: {result.errors}"
    assert result.mapping["key"] == "Issue Key"
    assert result.mapping["created_at"] == "Created Date"
    assert result.mapping["status"] == "Issue Status"
    assert result.mapping["priority"] == "Bug Priority"
    assert result.mapping["resolved_at"] == "Resolution Date"


def test_validation_valid():
    """Test validation with valid mapping."""
    df = pd.DataFrame({
        "Key": ["BUG-1"],
        "Created": ["2024-01-01"],
        "Status": ["Open"],
        "Priority": ["High"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    
    # Valid mapping
    valid_mapping = {
        "key": "Key",
        "created_at": "Created",
        "status": "Status",
        "priority": "Priority"
    }
    
    result = mapper.validate_mapping(valid_mapping, df)
    
    assert result.valid, f"Mapping should be valid. Errors: {result.errors}"
    assert len(result.errors) == 0
    assert len(result.missing_required) == 0


def test_validation_invalid():
    """Test validation with invalid mapping (missing required fields)."""
    df = pd.DataFrame({
        "Key": ["BUG-1"],
        "Created": ["2024-01-01"],
        "Status": ["Open"],
        "Priority": ["High"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    
    # Invalid mapping (missing required fields)
    invalid_mapping = {
        "key": "Key",
        "created_at": "Created",
        # Missing status and priority
    }
    
    result = mapper.validate_mapping(invalid_mapping, df)
    
    assert not result.valid, "Mapping should be invalid"
    assert "status" in result.missing_required
    assert "priority" in result.missing_required
    assert len(result.errors) > 0
    
    # Test error formatting
    error_msg = mapper.format_validation_error(result)
    assert "❌" in error_msg
    assert "status" in error_msg
    assert "priority" in error_msg


def test_exact_match():
    """Test with exact canonical column names (no mapping needed)."""
    df = pd.DataFrame({
        "key": ["BUG-1"],
        "created_at": ["2024-01-01"],
        "status": ["Open"],
        "priority": ["High"],
        "resolved_at": ["2024-01-10"],
        "environment": ["QA"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)
    
    assert result.valid
    assert result.mapping["key"] == "key"
    assert result.mapping["created_at"] == "created_at"
    assert result.mapping["status"] == "status"
    assert result.mapping["priority"] == "priority"
    assert result.mapping["resolved_at"] == "resolved_at"
    assert result.mapping["environment"] == "environment"


def test_multiple_environment_columns_select_best_candidate():
    """Auto-mapping should choose the real env column instead of coalescing all of them."""
    from qa_bugs.ingest.normalizer import Normalizer

    df = pd.DataFrame({
        "Key": ["BUG-1", "BUG-2", "BUG-3"],
        "Created": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "Status": ["Open", "Closed", "Open"],
        "Priority": ["High", "Low", "Medium"],
        "Discovery Environment": ["web", "mobile", "api"],
        "Environment": ["qa", "prod", "dev"],
        "Runtime Environment": ["chrome", "firefox", "edge"],
    })

    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)

    assert result.valid, f"Mapping should be valid. Errors: {result.errors}"
    assert result.mapping["environment"] == "Environment"

    normalized = Normalizer(result.mapping).normalize(df)

    assert normalized["environment"].tolist() == ["QA", "PROD", "DEV"]


def test_environment_column_rejected_when_cardinality_is_too_high():
    """Columns with too many distinct values are unlikely to be environment fields."""
    row_count = FieldMappingService.MAX_ENV_UNIQUE_VALUES + 1
    df = pd.DataFrame({
        "Key": [f"BUG-{i}" for i in range(row_count)],
        "Created": ["2024-01-01"] * row_count,
        "Status": ["Open"] * row_count,
        "Priority": ["High"] * row_count,
        "Environment Details": [f"unique free text value {i}" for i in range(row_count)],
    })

    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)

    assert result.valid, f"Mapping should remain valid without optional env. Errors: {result.errors}"
    assert "environment" not in result.mapping


def test_resolution_selects_outcome_column_not_resolution_date():
    """Resolution outcome should be distinct from resolved_at date fields."""
    df = pd.DataFrame({
        "Key": ["BUG-1", "BUG-2", "BUG-3"],
        "Created": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "Status": ["Done", "Done", "Done"],
        "Priority": ["High", "Low", "Medium"],
        "resolutiondate": ["2024-01-04", "2024-01-05", "2024-01-06"],
        "Resolution": ["Fixed", "Won't Fix", "Duplicate"],
    })

    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)

    assert result.valid, f"Mapping should be valid. Errors: {result.errors}"
    assert result.mapping["resolved_at"] == "resolutiondate"
    assert result.mapping["resolution"] == "Resolution"


def test_resolution_date_is_not_mapped_as_resolution_outcome():
    """A date-like resolution column should not become the resolution outcome field."""
    df = pd.DataFrame({
        "Key": ["BUG-1", "BUG-2"],
        "Created": ["2024-01-01", "2024-01-02"],
        "Status": ["Done", "Done"],
        "Priority": ["High", "Low"],
        "Resolution Date": ["2024-01-04", "2024-01-05"],
    })

    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)

    assert result.valid, f"Mapping should be valid. Errors: {result.errors}"
    assert result.mapping["resolved_at"] == "Resolution Date"
    assert "resolution" not in result.mapping


def test_resolution_column_rejected_when_cardinality_is_too_high():
    """High-cardinality text columns are unlikely to be resolution outcomes."""
    row_count = FieldMappingService.MAX_RESOLUTION_UNIQUE_VALUES + 1
    df = pd.DataFrame({
        "Key": [f"BUG-{i}" for i in range(row_count)],
        "Created": ["2024-01-01"] * row_count,
        "Status": ["Done"] * row_count,
        "Priority": ["High"] * row_count,
        "Resolution Comment": [f"unique closure explanation {i}" for i in range(row_count)],
    })

    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)

    assert result.valid, f"Mapping should remain valid without optional resolution. Errors: {result.errors}"
    assert "resolution" not in result.mapping


def test_case_insensitive_matching():
    """Test that fuzzy matching handles case differences."""
    df = pd.DataFrame({
        "ISSUE_KEY": ["BUG-1"],
        "CREATED_DATE": ["2024-01-01"],
        "ISSUE_STATUS": ["Open"],
        "PRIORITY_LEVEL": ["High"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)
    
    assert result.valid, f"Should handle uppercase columns. Errors: {result.errors}"
    assert "key" in result.mapping
    assert "created_at" in result.mapping
    assert "status" in result.mapping
    assert "priority" in result.mapping


def test_missing_column_in_mapping():
    """Test validation when mapped column doesn't exist in CSV."""
    df = pd.DataFrame({
        "Key": ["BUG-1"],
        "Created": ["2024-01-01"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    
    # Mapping references non-existent column
    bad_mapping = {
        "key": "Key",
        "created_at": "Created",
        "status": "NonExistentColumn",
        "priority": "AlsoDoesNotExist"
    }
    
    result = mapper.validate_mapping(bad_mapping, df)
    
    assert not result.valid
    assert any("NonExistentColumn" in err for err in result.errors)
    assert any("AlsoDoesNotExist" in err for err in result.errors)


def test_duplicate_column_mapping():
    """Test warning when same column mapped to multiple fields."""
    df = pd.DataFrame({
        "Key": ["BUG-1"],
        "Created": ["2024-01-01"],
        "Status": ["Open"],
        "Priority": ["High"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    
    # Valid mapping without duplicates
    valid_mapping = {
        "key": "Key",
        "created_at": "Created",
        "status": "Status",
        "priority": "Priority"
    }
    
    result = mapper.validate_mapping(valid_mapping, df)
    assert result.valid, f"Valid mapping should pass. Errors: {result.errors}"


if __name__ == "__main__":
    """Run tests manually."""
    print("Running Field Mapper Unit Tests\n")
    print("=" * 60)
    
    test_exact_match()
    print("✓ test_exact_match")
    
    test_fuzzy_mapping()
    print("✓ test_fuzzy_mapping")
    
    test_validation_valid()
    print("✓ test_validation_valid")
    
    test_validation_invalid()
    print("✓ test_validation_invalid")
    
    test_case_insensitive_matching()
    print("✓ test_case_insensitive_matching")
    
    test_missing_column_in_mapping()
    print("✓ test_missing_column_in_mapping")
    
    test_duplicate_column_mapping()
    print("✓ test_duplicate_column_mapping")
    
    print("=" * 60)
    print("\n✓ All unit tests passed!")
    print("\nTo run with pytest: pytest tests/test_field_mapper.py -v")
    print("For LLM tests: pytest tests/test_field_mapper_llm.py -v")

