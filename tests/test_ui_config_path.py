"""Test UI configuration path resolution."""

import pytest
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_ui_can_find_config_file():
    """Test that UI app can locate the example config file."""
    # Simulate what the UI does to find config
    ui_app_path = Path(__file__).parent.parent / "src" / "qa_bugs" / "ui" / "app.py"
    assert ui_app_path.exists(), f"UI app file not found at {ui_app_path}"
    
    # Navigate to project root (same logic as in app.py)
    project_root = ui_app_path.parent.parent.parent.parent
    config_path = project_root / "configs" / "example.config.yml"
    
    assert config_path.exists(), (
        f"Config file not found at {config_path}. "
        f"UI app will fail to load config. "
        f"Project root detected as: {project_root}"
    )
    
    # Verify it's the actual config file we expect
    assert config_path.name == "example.config.yml"
    assert config_path.is_file()
    
    # Verify we can read it
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        config_dict = yaml.safe_load(f)
    
    # Basic validation
    assert config_dict is not None
    assert "fields_mapping" in config_dict
    assert "metrics" in config_dict


def test_ui_config_path_matches_cli():
    """Ensure UI and CLI use the same configs/ directory."""
    ui_app_path = Path(__file__).parent.parent / "src" / "qa_bugs" / "ui" / "app.py"
    cli_app_path = Path(__file__).parent.parent / "src" / "qa_bugs" / "cli" / "cli.py"
    
    # Both should resolve to the same project root
    ui_project_root = ui_app_path.parent.parent.parent.parent
    cli_project_root = cli_app_path.parent.parent.parent.parent
    
    assert ui_project_root == cli_project_root, (
        "UI and CLI should resolve to the same project root"
    )
    
    # Both should find the same configs directory
    ui_configs = ui_project_root / "configs"
    cli_configs = cli_project_root / "configs"
    
    assert ui_configs == cli_configs
    assert ui_configs.exists()
    assert (ui_configs / "example.config.yml").exists()


def test_ui_import_works():
    """Test that we can import the UI app module without errors."""
    try:
        from qa_bugs.ui import app
        assert hasattr(app, 'load_config'), "load_config function should exist"
        assert hasattr(app, 'main'), "main function should exist"
    except ImportError as e:
        pytest.fail(f"Failed to import UI app: {e}")


if __name__ == "__main__":
    # Run tests standalone
    print("Testing UI config path resolution...")
    test_ui_can_find_config_file()
    print("✓ Config file found")
    
    test_ui_config_path_matches_cli()
    print("✓ UI and CLI use same configs directory")
    
    test_ui_import_works()
    print("✓ UI module imports successfully")
    
    print("\n✓ All UI config path tests passed!")
