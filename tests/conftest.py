import pandas as pd
import pytest
from datetime import datetime, timedelta

@pytest.fixture
def now_ts():
    return datetime(2025, 10, 1, 12, 0, 0)

@pytest.fixture
def sample_df(now_ts):
    base = now_ts - timedelta(days=10)
    rows = [
        {"key": "BUG-1", "created_at": base, "resolved_at": base + timedelta(days=2), "status": "Closed", "priority": "High", "environment": "QA"},
        {"key": "BUG-2", "created_at": base + timedelta(days=1), "resolved_at": None, "status": "In Progress", "priority": "Medium", "environment": "DEV"},
        {"key": "BUG-3", "created_at": base + timedelta(days=2), "resolved_at": base + timedelta(days=5), "status": "Closed", "priority": "Low", "environment": "PROD"},
    ]
    return pd.DataFrame(rows)
