import pandas as pd
from typing import List, Optional

def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return pd.to_datetime(s).normalize()
    except Exception:
        return None

def apply_filters(df: pd.DataFrame, since: Optional[str]=None, until: Optional[str]=None, exclude_statuses: List[str]=None) -> pd.DataFrame:
    d = df.copy()
    s = _parse_date(since)
    u = _parse_date(until)

    if "created_at" in d.columns:
        d["created_at_norm"] = pd.to_datetime(d["created_at"], errors="coerce").dt.normalize()
        if s is not None:
            d = d[d["created_at_norm"] >= s]
        if u is not None:
            d = d[d["created_at_norm"] <= u]
        d = d.drop(columns=["created_at_norm"])

    if exclude_statuses and "status" in d.columns:
        ex = set([str(x) for x in exclude_statuses])
        d = d[~d["status"].astype("string").isin(ex)]

    return d.reset_index(drop=True)
