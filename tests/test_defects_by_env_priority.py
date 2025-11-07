import pandas as pd
from qa_bugs.metrics.defects_by_env_priority import DefectsByEnvPriority


def test_env_priority_unknown_first():
    df = pd.DataFrame([
        {"environment": "X1", "priority": "High"},
        {"environment": "X1", "priority": "Low"},
        {"environment": "QA", "priority": "High"},
        {"environment": "DEV", "priority": "High"},
        {"environment": "DEV", "priority": "Low"},
        {"environment": "PROD", "priority": "Low"},
        {"environment": "Y2", "priority": "Low"},
    ])
    metric = DefectsByEnvPriority()
    params = {"env_order": ["DEV", "QA", "PROD"]}
    res = metric.compute(df, params)
    tbl = res.tables["env_priority"]
    # Extract order as it appears after compute
    env_order_list = tbl.groupby("environment").agg({"count":"sum"}).reset_index()["environment"].tolist()
    # Unknown envs X1 (2 rows), Y2 (1) -> X1 first then Y2, then configured DEV, QA, PROD
    assert env_order_list[:5][0] == "X1"
    assert env_order_list[:5][1] == "Y2"
    assert all(e in env_order_list for e in ["DEV","QA","PROD"])
