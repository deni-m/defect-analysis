import pandas as pd
import re

class Normalizer:
    CANON = {
        "key", "created_at", "resolved_at",
        "status", "priority", "fix_version",
        "environment", "category"
    }

    def __init__(self, mapping: dict):
        self.mapping = mapping or {}

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        # Build a lookup allowing loose matching (strip brackets, lowercase, remove spaces and punctuation)
        def _norm_label(s: str) -> str:
            s = s.lower()
            # remove brackets content markers like [created] or [resolutiondate]
            s = re.sub(r"\s*\[[^]]*\]", "", s)  # drop bracketed suffixes
            # collapse non-alphanumeric
            s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
            return s
        normalized_cols = {_norm_label(c): c for c in d.columns}

        out = {}
        for canon, desired in self.mapping.items():
            # direct match first
            if desired in d.columns:
                out[canon] = d[desired]
                continue
            # try normalized match
            norm_desired = _norm_label(desired)
            if norm_desired in normalized_cols:
                out[canon] = d[normalized_cols[norm_desired]]
                continue
            # fallback: attempt partial startswith among normalized columns
            picked = None
            for nrm, orig in normalized_cols.items():
                if nrm.startswith(norm_desired):
                    picked = orig
                    break
            if picked:
                out[canon] = d[picked]
            else:
                out[canon] = None
        out_df = pd.DataFrame(out)

        # всередині normalize(), після створення out_df
        for col in ("created_at", "resolved_at"):
            if col in out_df.columns:
                out_df[col] = pd.to_datetime(out_df[col], errors="coerce", utc=True).dt.tz_convert(None)


        for col in ("created_at", "resolved_at"):
            if col in out_df.columns:
                out_df[col] = pd.to_datetime(out_df[col], errors="coerce")

        for col in ("status", "priority", "fix_version", "environment", "category", "key"):
            if col in out_df.columns:
                out_df[col] = out_df[col].astype("string").fillna(pd.NA)

        if "environment" in out_df.columns:
            out_df["environment"] = out_df["environment"].str.upper()

        return out_df
