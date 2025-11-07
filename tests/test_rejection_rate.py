import pandas as pd
from qa_bugs.metrics.rejection_rate import RejectionRate


def test_rejection_rate_basic():
    df = pd.DataFrame([
        {"status": "Rejected"},
        {"status": "Closed"},
        {"status": "Cancelled"},
    ])
    metric = RejectionRate()
    cfg = {"metrics": {"params": {"rejection_rate": {"rejected_statuses": ["Rejected", "Cancelled"]}}}}
    res = metric.compute(df, cfg)
    summary = res.tables["rejection_summary"].iloc[0]
    assert summary["rejected"] == 2
    assert summary["total"] == 3
    assert round(summary["rejection_percent"],2) == round(2/3*100,2)
