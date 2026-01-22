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
    
    return result


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
