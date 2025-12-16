"""Test field mapper logging behavior."""

import pandas as pd
import logging
import pytest
from io import StringIO

from qa_bugs.ingest.field_mapper import FieldMappingService


@pytest.fixture
def log_capture():
    """Capture log output for testing."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    # Get the field_mapper logger
    logger = logging.getLogger('qa_bugs.ingest.field_mapper')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    
    yield log_stream
    
    logger.removeHandler(handler)


def test_logging_fuzzy_matching_only(log_capture):
    """Test logging when only fuzzy matching is used (no LLM)."""
    df = pd.DataFrame({
        "IssueKey": ["B-1", "B-2"],
        "CreatedDate": ["2024-01-01", "2024-01-02"],
        "Status": ["Open", "Closed"],
        "Priority": ["High", "Low"]
    })
    
    # Create mapper without LLM
    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df, sample_rows=2)
    
    log_output = log_capture.getvalue()
    
    # Verify logging messages
    assert "Auto-detecting field mapping" in log_output
    assert "LLM service not available, using fuzzy matching only" in log_output
    assert "Starting fuzzy matching detection" in log_output
    assert "Fuzzy matching completed" in log_output
    assert f"detected {len(result.mapping)} field mappings" in log_output
    assert "Fuzzy mapping validation:" in log_output
    
    # Should not have LLM-related messages
    assert "LLM service is enabled" not in log_output
    assert "Attempting LLM-based field mapping" not in log_output


def test_logging_shows_detected_fields(log_capture):
    """Test that logging shows which fields were detected."""
    df = pd.DataFrame({
        "Key": ["B-1"],
        "Created": ["2024-01-01"],
        "Status": ["Open"],
        "Priority": ["High"]
    })
    
    # Set debug level to see fuzzy match details
    logger = logging.getLogger('qa_bugs.ingest.field_mapper')
    logger.setLevel(logging.DEBUG)
    
    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)
    
    log_output = log_capture.getvalue()
    
    # Should log individual fuzzy matches at debug level
    assert "Fuzzy match:" in log_output or "Fuzzy matching completed" in log_output
    assert "score:" in log_output or "field mappings" in log_output


def test_logging_validation_results(log_capture):
    """Test that validation results are logged."""
    df = pd.DataFrame({
        "IssueKey": ["B-1"],
        "CreatedDate": ["2024-01-01"],
        "Status": ["Open"],
        "Priority": ["High"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)
    
    log_output = log_capture.getvalue()
    
    # Should log validation results
    assert "validation:" in log_output.lower()
    assert f"valid={result.valid}" in log_output
    assert f"errors={len(result.errors)}" in log_output
    assert f"warnings={len(result.warnings)}" in log_output


def test_logging_fallback_with_error(log_capture):
    """Test logging when LLM fails and fallback is triggered."""
    df = pd.DataFrame({
        "Key": ["B-1"],
        "Created": ["2024-01-01"],
        "Status": ["Open"],
        "Priority": ["High"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    # Simulate fallback by calling _fuzzy_detect_mapping with error
    result = mapper._fuzzy_detect_mapping(df, error="Simulated LLM failure")
    
    log_output = log_capture.getvalue()
    
    # Should log the fallback reason
    assert "Starting fuzzy matching fallback" in log_output
    assert "Simulated LLM failure" in log_output


def test_logging_llm_prompt_and_response(log_capture):
    """Test that LLM prompt and response are logged at DEBUG level."""
    from unittest.mock import Mock
    
    df = pd.DataFrame({
        "IssueKey": ["B-1"],
        "CreatedDate": ["2024-01-01"],
        "Status": ["Open"],
        "Priority": ["High"]
    })
    
    # Create mock LLM service
    mock_llm = Mock()
    mock_llm.is_enabled.return_value = True
    mock_llm.deployment = "gpt-4o-mini"
    
    # Mock successful response with correct YAML format
    yaml_response = """fields_mapping:
  key: IssueKey
  created_at: CreatedDate
  status: Status
  priority: Priority
"""
    mock_llm._chat.return_value = (True, yaml_response, None)
    
    mapper = FieldMappingService(llm_service=mock_llm)
    result = mapper.auto_detect_mapping(df, sample_rows=1)
    
    log_output = log_capture.getvalue()
    
    # Verify LLM process is logged
    assert "LLM service is enabled" in log_output
    assert "Attempting LLM-based field mapping" in log_output
    assert "LLM prompt:" in log_output
    assert "LLM call successful" in log_output
    assert "LLM response:" in log_output
    
    # Verify prompt content appears in logs
    assert "IssueKey" in log_output  # Should be in prompt
    assert "fields_mapping:" in log_output  # Should be in response
    
    # Verify it succeeded (no fallback)
    assert "Starting fuzzy matching fallback" not in log_output


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
    
    print("Testing logging output...")
    df = pd.DataFrame({
        "IssueKey": ["B-1", "B-2"],
        "CreatedDate": ["2024-01-01", "2024-01-02"],
        "Status": ["Open", "Closed"],
        "Priority": ["High", "Low"]
    })
    
    mapper = FieldMappingService(llm_service=None)
    result = mapper.auto_detect_mapping(df)
    
    print(f"\nResult: valid={result.valid}, fields={len(result.mapping)}")
    print("✓ Logging test completed")

