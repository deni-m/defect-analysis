import pandas as pd
import re
from typing import Optional, Dict

class Normalizer:
    CANON = {
        "key", "created_at", "resolved_at",
        "status", "priority", "fix_version",
        "environment", "category"
    }

    def __init__(self, mapping: dict, env_value_mapping: Optional[Dict[str, str]] = None):
        """
        Initialize Normalizer.
        
        Args:
            mapping: Field name mapping (canonical -> CSV column)
            env_value_mapping: Optional environment value mapping (original_value -> canonical_value)
        """
        self.mapping = mapping or {}
        self.env_value_mapping = env_value_mapping or {}

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

        for col in ("status", "priority", "fix_version", "environment", "key"):
            if col in out_df.columns:
                out_df[col] = out_df[col].astype("string").fillna(pd.NA)

        # Apply environment value mapping first (before uppercasing)
        if "environment" in out_df.columns and self.env_value_mapping:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Normalizer: Applying env_value_mapping: {self.env_value_mapping}")
            unique_before = out_df["environment"].dropna().unique().tolist()
            logger.info(f"Normalizer: Unique environments BEFORE mapping: {unique_before}")
            
            out_df["environment"] = out_df["environment"].map(
                lambda x: self.env_value_mapping.get(x, x) if pd.notna(x) else x
            )
            
            unique_after = out_df["environment"].dropna().unique().tolist()
            logger.info(f"Normalizer: Unique environments AFTER mapping: {unique_after}")
        elif "environment" in out_df.columns:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Normalizer: env_value_mapping is empty or None: {self.env_value_mapping}")

        # Then uppercase all environment values
        if "environment" in out_df.columns:
            out_df["environment"] = out_df["environment"].str.upper()

        return out_df
