"""Kevin's kill switch for the nightly run (EATP-037).

Four knobs, editable from his phone: `enabled`, `skip_next_run`,
`pause_until` and `weekly_cap_pct`. The PC-side runner reads them before
every run and **fails closed**: if the file is missing, corrupt or
unreadable the defaults apply, and the default is *off*. A broken switch
must never spend Kevin's Claude quota.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, ValidationError

from rove import config
from rove.storage import read_json, write_json


class NightlySettings(BaseModel):
    enabled: bool = False
    skip_next_run: bool = False
    pause_until: date | None = None
    weekly_cap_pct: int = Field(default=70, ge=10, le=100)
    updated_at: datetime | None = None


class RunDecision(BaseModel):
    allowed: bool
    reason: str


def today_local() -> date:
    """Kevin's calendar day (Mexico City, fixed UTC-6), not the VM's UTC day."""
    return datetime.now(UTC).astimezone(config.KEVIN_TIMEZONE).date()


def load() -> NightlySettings:
    """Current settings; any problem reading them yields the safe defaults (off)."""
    raw = read_json(config.NIGHTLY_SETTINGS_FILE, default=None)
    if not isinstance(raw, dict):
        return NightlySettings()
    try:
        return NightlySettings(**raw)
    except (TypeError, ValueError, ValidationError):
        return NightlySettings()


def save(settings: NightlySettings) -> NightlySettings:
    settings = settings.model_copy(update={"updated_at": datetime.now(UTC)})
    write_json(config.NIGHTLY_SETTINGS_FILE, settings.model_dump(mode="json"))
    return settings


def update(**changes: object) -> NightlySettings:
    """Apply a partial change on top of the current settings and persist it.

    Raises `ValidationError` for an invalid value (e.g. a cap outside 10-100)
    without touching the file.
    """
    merged = load().model_dump()
    merged.update(changes)
    merged.pop("updated_at", None)
    return save(NightlySettings(**merged))


def decide(settings: NightlySettings, today: date | None = None) -> RunDecision:
    """May the runner run now? Order: off, skip-next-run, paused, else go."""
    today = today or today_local()
    if not settings.enabled:
        return RunDecision(allowed=False, reason="apagado")
    if settings.skip_next_run:
        return RunDecision(allowed=False, reason="saltar la próxima corrida")
    if settings.pause_until is not None and today <= settings.pause_until:
        return RunDecision(allowed=False, reason=f"en pausa hasta {settings.pause_until.isoformat()}")
    return RunDecision(allowed=True, reason="encendido")


def consume_skip() -> NightlySettings:
    """The runner calls this once it has honoured `skip_next_run`, so the skip
    only ever covers a single run."""
    current = load()
    if not current.skip_next_run:
        return current
    return save(current.model_copy(update={"skip_next_run": False}))
