"""Actually sends a previously-prepared application (EATP-034, ADR-011).

Re-drives the browser against a fresh page — the prepare-time session isn't
kept alive across the gap until Kevin (or EATP-035's sweep) sends it, which
can be hours or days later. Reuses the exact answers stored on the
`ApplicationEntry` rather than re-asking the AI: whatever was reviewed (or
left untouched and trusted, per Kevin's own call) is what actually gets
sent, never a fresh, possibly-different, answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import BrowserContext, sync_playwright

from rove import config
from rove.apply.browser import (
    fill_form,
    identity_values_from_profile,
    read_form,
    resolve_apply_url,
    submit_form,
)
from rove.apply.prepare import NAVIGATION_TIMEOUT_MS, POST_LOAD_SETTLE_MS
from rove.apply.store import ApplicationEntry, ApplicationStatus, record_entry
from rove.config import get_logger
from rove.models import Job
from rove.profile import Profile

logger = get_logger(__name__)


def submit_application(
    job: Job,
    profile: Profile,
    entry: ApplicationEntry,
    resume_path: Path | None = None,
    context: BrowserContext | None = None,
) -> ApplicationEntry:
    """Fills and submits `job`'s real apply form using `entry.answers`.
    Persists and returns the resulting entry — never raises; any failure
    becomes a `failed` (retryable) entry rather than crashing the caller
    (the dashboard's manual "send" button, or EATP-035's daily sweep).

    `context` is normally launched internally (production path); tests pass
    one in with `context.route(...)` already wired, so no real network call
    is ever needed to exercise this function end-to-end (CLAUDE.md §7)."""
    resume = resume_path or config.RESUME_FILE

    if context is not None:
        updated = _submit_with_context(context, job, profile, entry, resume)
        record_entry(updated)
        return updated

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            owned_context = browser.new_context()
            try:
                updated = _submit_with_context(owned_context, job, profile, entry, resume)
            finally:
                owned_context.close()
        finally:
            browser.close()
    record_entry(updated)
    return updated


def _submit_with_context(
    context: BrowserContext, job: Job, profile: Profile, entry: ApplicationEntry, resume: Path
) -> ApplicationEntry:
    try:
        page = context.new_page()
        try:
            apply_url = resolve_apply_url(job.url, job.source)
            page.goto(apply_url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(POST_LOAD_SETTLE_MS)
            result = read_form(page, job.source)

            if result.has_captcha or not result.fields:
                reason = (
                    "reCAPTCHA (or similar) on the submit form"
                    if result.has_captcha
                    else (result.blocked_reason or "no application form found on this page")
                )
                return _updated(entry, ApplicationStatus.MANUAL_REQUIRED, reason)

            identity_values = identity_values_from_profile(profile)
            unresolved = fill_form(page, result, identity_values, entry.answers, resume)
            if unresolved:
                return _updated(entry, ApplicationStatus.FAILED, "; ".join(unresolved))

            if submit_form(page, result):
                return _updated(entry, ApplicationStatus.SUBMITTED, None)
            return _updated(entry, ApplicationStatus.FAILED, "submit click did not reach a confirmation")
        finally:
            page.close()
    except Exception as error:  # noqa: BLE001 - navigation/DOM errors, retried next sweep
        logger.warning("submit_application: %s (%s) failed: %s", job.company, job.title, error)
        return _updated(entry, ApplicationStatus.FAILED, str(error))


def _updated(entry: ApplicationEntry, status: ApplicationStatus, note: str | None) -> ApplicationEntry:
    return entry.model_copy(update={"status": status, "note": note, "updated_at": datetime.now(UTC)})
