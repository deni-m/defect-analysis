from __future__ import annotations
import pandas as pd
from typing import Optional

def _to_aware(ts_str: Optional[str], tz: str):
    if not ts_str:
        return None
    ts = pd.to_datetime(ts_str, errors="coerce")
    if ts is None or pd.isna(ts):
        return None
    if ts.tz is None:
        return ts.tz_localize(tz)
    return ts.tz_convert(tz)

def apply_filters(df: pd.DataFrame, since: str | None, until: str | None, release: str | None, tz: str = "UTC") -> pd.DataFrame:
    out = df.copy()
    if "created_at" in out.columns:
        out["created_at"] = pd.to_datetime(out["created_at"], errors="coerce")
        if out["created_at"].dt.tz is None:
            out["created_at"] = out["created_at"].dt.tz_localize(tz)
        else:
            out["created_at"] = out["created_at"].dt.tz_convert(tz)
    since_ts = _to_aware(since, tz) if since else None
    until_ts = _to_aware(until, tz) if until else None
    if until_ts is not None:
        until_ts = until_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    if since_ts is not None:
        out = out[out["created_at"] >= since_ts]
    if until_ts is not None:
        out = out[out["created_at"] <= until_ts]
    if release and "fix_version" in out.columns:
        out = out[out["fix_version"].fillna('').str.contains(release, na=False)]
    return out.reset_index(drop=True)
