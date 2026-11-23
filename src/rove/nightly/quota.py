"""Claude usage as the runner sees it (EATP-037).

The number comes from the same free "how much have I used" endpoint Pulse
reads (`api.anthropic.com/api/oauth/usage`), through `pc/nightly/read_quota.ps1`
on Kevin's Windows side — it spends no tokens and never refreshes the login.
The runner **fails closed**: an unreadable quota means it does not run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Quota:
    session_pct: float
    weekly_pct: float
    session_resets_at: str | None = None
    weekly_resets_at: str | None = None


def parse_quota_error(text: str) -> tuple[int, int]:
    """(http_status, retry_after_seconds) from a failed reading; (0, 0) if unknown."""
    try:
        data: Any = json.loads((text or "").strip().splitlines()[-1])
        return int(data.get("status") or 0), int(data.get("retry_after") or 0)
    except (json.JSONDecodeError, IndexError, TypeError, ValueError, AttributeError):
        return 0, 0


def parse_quota(text: str) -> Quota | None:
    """Parse the PowerShell script's one-line JSON. `None` for anything unusable."""
    try:
        data: Any = json.loads((text or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    if not isinstance(data, dict) or data.get("ok") is not True:
        return None
    try:
        return Quota(
            session_pct=float(data["session"]),
            weekly_pct=float(data["weekly"]),
            session_resets_at=data.get("session_resets_at"),
            weekly_resets_at=data.get("weekly_resets_at"),
        )
    except (KeyError, TypeError, ValueError):
        return None
