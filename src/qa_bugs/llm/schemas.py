from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List


class BugCritique(BaseModel):
    issue_key: str
    classification: str = Field(description="env_leak|bad_repro|wrong_priority|flaky|duplicate|other")
    quality_score: int = Field(ge=0, le=100)
    root_cause_guess: str | None = None
    missing_info: List[str] = []
    action_items: List[str] = []


class BugsSummary(BaseModel):
    key_insights: list[str] = []
    risks: list[str] = []
    recommendations: list[str] = []
