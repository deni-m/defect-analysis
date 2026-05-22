"""Test environment value mapping functionality."""
import pandas as pd
from qa_bugs.ingest.env_value_mapper import EnvironmentValueMapper


def test_fuzzy_mapping():
    """Test fuzzy keyword matching without LLM."""
    print("\n=== Testing Fuzzy Keyword Matching ===")
    
    # Sample environment values
    unique_values = [
        "production",
        "PROD",
        "qa-server",
        "testing",
        "dev-env",
        "development",
        "staging-1",
        "uat-server",
        "localhost"
    ]
    
    # Initialize mapper without LLM
    mapper = EnvironmentValueMapper(llm_service=None)
    
    # Auto-map values
    result = mapper.auto_map_values(unique_values, allow_passthrough=True)
    
    # Display results
    print(f"\nSuccess: {result.success}")
    print(f"Method: {result.method_used}")
    print(f"\nValue Mappings:")
    for orig, mapped in sorted(result.value_mapping.items()):
        print(f"  {orig:20} -> {mapped}")
    
    if result.warnings:
        print(f"\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    
    if result.errors:
        print(f"\nErrors:")
        for error in result.errors:
            print(f"  - {error}")
    
    assert result.value_mapping["production"] == "PROD"
    assert result.value_mapping["qa-server"] == "QA-SERVER"
    assert result.value_mapping["dev-env"] == "DEV-ENV"


def test_non_prod_values_map_to_non_prod_not_dev():
    """Broad non-production labels should not be collapsed into DEV."""
    mapper = EnvironmentValueMapper(llm_service=None)

    result = mapper.auto_map_values([
        "Dev-A",
        "ETE",
        "Non-Prod",
        "Non-Production",
        "Production",
        "non-prod",
    ])

    assert result.success
    assert result.value_mapping["Dev-A"] == "DEV-A"
    assert result.value_mapping["ETE"] == "ETE"
    assert result.value_mapping["Non-Prod"] == "NON_PROD"
    assert result.value_mapping["Non-Production"] == "NON_PROD"
    assert result.value_mapping["Production"] == "PROD"
    assert result.value_mapping["non-prod"] == "NON_PROD"


def test_unknown_environment_values_are_preserved():
    """Domain-specific env labels should remain visible for recommendations."""
    mapper = EnvironmentValueMapper(llm_service=None)

    result = mapper.auto_map_values(["Sandbox-A", "TeamBlue"])

    assert result.success
    assert result.value_mapping["Sandbox-A"] == "SANDBOX-A"
    assert result.value_mapping["TeamBlue"] == "TEAMBLUE"


def test_specific_environment_variants_are_preserved_by_default():
    """Specific env labels carry useful signal and should not be over-collapsed."""
    mapper = EnvironmentValueMapper(llm_service=None)

    result = mapper.auto_map_values(["Dev-A", "QA-Blue", "prod-east"])

    assert result.success
    assert result.value_mapping["Dev-A"] == "DEV-A"
    assert result.value_mapping["QA-Blue"] == "QA-BLUE"
    assert result.value_mapping["prod-east"] == "PROD-EAST"


def test_exact_and_safe_aliases_are_mapped_with_high_confidence():
    """Only obvious standalone aliases should collapse to standard categories."""
    mapper = EnvironmentValueMapper(llm_service=None)

    result = mapper.auto_map_values([
        "dev",
        "development",
        "qa",
        "testing",
        "uat",
        "staging",
        "production",
        "prod",
    ])

    assert result.success
    assert result.value_mapping["dev"] == "DEV"
    assert result.value_mapping["development"] == "DEV"
    assert result.value_mapping["qa"] == "QA"
    assert result.value_mapping["testing"] == "QA"
    assert result.value_mapping["uat"] == "UAT"
    assert result.value_mapping["staging"] == "STAGE"
    assert result.value_mapping["production"] == "PROD"
    assert result.value_mapping["prod"] == "PROD"


def test_normalizer_integration():
    """Test environment value mapping integration with Normalizer."""
    print("\n\n=== Testing Normalizer Integration ===")
    
    from qa_bugs.ingest.normalizer import Normalizer
    
    # Sample data with various environment names
    data = {
        "Key": ["BUG-1", "BUG-2", "BUG-3", "BUG-4", "BUG-5"],
        "Created": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
        "Status": ["Open", "Closed", "Open", "In Progress", "Done"],
        "Priority": ["High", "Medium", "Low", "High", "Medium"],
        "Environment": ["production", "qa-server", "testing", "dev-env", "PROD"]
    }
    
    df = pd.DataFrame(data)
    print("\nOriginal Data:")
    print(df[["Key", "Environment"]])
    
    # Define field mapping
    field_mapping = {
        "key": "Key",
        "created_at": "Created",
        "status": "Status",
        "priority": "Priority",
        "environment": "Environment"
    }
    
    # Create environment value mapping (simulating auto-mapping result)
    env_value_mapping = {
        "production": "PROD",
        "qa-server": "QA",
        "testing": "QA",
        "dev-env": "DEV",
        "PROD": "PROD"
    }
    
    # Initialize normalizer with environment mapping
    normalizer = Normalizer(
        mapping=field_mapping,
        env_value_mapping=env_value_mapping
    )
    
    # Normalize data
    df_normalized = normalizer.normalize(df)
    
    print("\nNormalized Data:")
    print(df_normalized[["key", "environment"]])
    
    print("\nEnvironment Value Transformations:")
    for orig in data["Environment"]:
        mapped = env_value_mapping.get(orig, orig.upper())
        print(f"  {orig:20} -> {mapped}")


if __name__ == "__main__":
    # Run tests
    print("=" * 60)
    print("ENVIRONMENT VALUE MAPPING TESTS")
    print("=" * 60)
    
    # Test 1: Fuzzy matching
    result = test_fuzzy_mapping()
    
    # Test 2: Normalizer integration
    test_normalizer_integration()
    
    print("\n" + "=" * 60)
    print("TESTS COMPLETED")
    print("=" * 60)
