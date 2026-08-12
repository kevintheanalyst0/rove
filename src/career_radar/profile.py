"""Typed loader for `profile.toml` — who Kevin is, for the AI prompt and matcher.

The human-readable source of truth is `docs/governance/CANDIDATE-PROFILE.md`;
this loads its machine twin. See CANDIDATE-PROFILE.md if a field here looks
surprising — this file only encodes it, it doesn't decide it.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from career_radar.config import PROFILE_FILE


class Skills(BaseModel):
    bi_and_analytics: list[str]
    data_and_automation: list[str]


class Priority(BaseModel):
    salary_is_priority: bool
    seniority_is_priority: bool
    overqualification_is_positive: bool
    partial_skill_match_is_good: bool
    statement: str


class Profile(BaseModel):
    name: str
    location: str
    open_to_remote_scope: str
    current_role: str
    background: str
    english_level: str
    career_goal: str
    target_roles: list[str]
    skills: Skills
    priority: Priority


@lru_cache(maxsize=1)
def load_profile(path: str | Path = PROFILE_FILE) -> Profile:
    """Load and validate `profile.toml`. Cached — it's static within a run."""
    with open(path, "rb") as file:
        data = tomllib.load(file)
    return Profile(**data)
