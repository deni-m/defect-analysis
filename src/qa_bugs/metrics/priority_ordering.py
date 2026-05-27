from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pandas as pd


_SEMANTIC_RANKS = (
    (0, {"showstopper", "blocker"}),
    (1, {"critical", "highest", "p0", "sev1"}),
    (2, {"major", "high", "p1", "sev2"}),
    (3, {"average", "medium", "moderate", "normal", "p2", "sev3"}),
    (4, {"minor", "low", "p3", "sev4"}),
    (5, {"trivial", "lowest", "cosmetic", "p4", "sev5"}),
    (99, {"tbd", "undefined", "unknown"}),
)


def normalize_priority(value: Any) -> str:
    if pd.isna(value):
        return "TBD"
    priority = str(value).strip()
    return priority or "TBD"


def ordered_priorities(values: Iterable[Any], profile: Any = None) -> list[str]:
    """Return priorities ordered by profile, numeric prefix, or severity keywords."""
    priorities = list(dict.fromkeys(normalize_priority(value) for value in values))
    if not priorities:
        return []

    if _has_numeric_prefix(priorities):
        return sorted(priorities, key=_priority_sort_key)

    profile_order = _profile_priority_order(profile)
    if profile_order:
        ordered = [priority for priority in profile_order if priority in priorities]
        ordered.extend(sorted((priority for priority in priorities if priority not in ordered), key=_priority_sort_key))
        return ordered

    return sorted(priorities, key=_priority_sort_key)


def apply_priority_order(df: pd.DataFrame, column: str = "priority", profile: Any = None) -> tuple[pd.DataFrame, list[str]]:
    ordered = ordered_priorities(df[column].tolist(), profile=profile)
    result = df.copy()
    result[column] = pd.Categorical(result[column].map(normalize_priority), categories=ordered, ordered=True)
    return result.sort_values(column), ordered


def _profile_priority_order(profile: Any) -> list[str]:
    priority_profile = getattr(profile, "priority_profile", None)
    severity_order = getattr(priority_profile, "severity_order", None)
    if not severity_order:
        return []
    return [normalize_priority(priority) for priority in severity_order]


def _has_numeric_prefix(priorities: list[str]) -> bool:
    return any(re.match(r"^\s*\d+\s*[-_.:)]", priority) for priority in priorities)


def _priority_sort_key(priority: str) -> tuple[int, int, str]:
    prefixed = re.match(r"^\s*(\d+)\s*[-_.:)]\s*(.*)$", priority)
    if prefixed:
        return (0, int(prefixed.group(1)), prefixed.group(2).casefold())

    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", priority.casefold())
        if token
    }
    for rank, keywords in _SEMANTIC_RANKS:
        if tokens & keywords:
            return (1, rank, priority.casefold())
    return (2, 999, priority.casefold())
