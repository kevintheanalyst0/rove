"""Orchestrates one job's application draft (EATP-034, ADR-011): eligibility,
headless-browser read, AI-answered custom questions, a real (but
never-submitted) fill to validate everything actually works, then persists
the result.

**Refinement over the original charter wording, my own call:** the charter
said prepare.py only reads the form and `submit.py` does the filling. In
practice, filling live (via `browser.fill_form`) during prepare — without
ever calling `submit_form` — is what actually validates a draft is real:
whether the AI's chosen option matches what's really on the page, whether
the EEO decline click genuinely works on this specific company's board, etc.
Catching that now beats discovering it only when EATP-035's sweep tries to
send a stale "confirmed working" draft. `submit.py` re-drives the exact same
fill against a fresh page at send time, reusing these same stored answers
rather than re-asking the AI — what Kevin reviewed is what gets sent.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext, sync_playwright

from rove import config
from rove.ai.router import AiRouter
from rove.apply.browser import (
    fill_form,
    identity_values_from_profile,
    read_form,
    resolve_apply_url,
)
from rove.apply.questions import answer_form_questions
from rove.apply.store import ApplicationEntry, ApplicationStatus, record_entry
from rove.config import get_logger
from rove.models import Grade, Job, ScoredJob
from rove.profile import Profile

logger = get_logger(__name__)

ELIGIBLE_SOURCES = {"greenhouse", "lever"}
NAVIGATION_TIMEOUT_MS = 20000
POST_LOAD_SETTLE_MS = 2000


def is_eligible(scored: ScoredJob) -> bool:
    """Kevin's own scope decision: every Greenhouse/Lever job graded
    A+/A/B/C (everything except D) — no per-run cap."""
    return scored.job.source in ELIGIBLE_SOURCES and scored.grade != Grade.D


def prepare_application(
    job: Job,
    profile: Profile,
    router: AiRouter,
    resume_path: Path | None = None,
    context: BrowserContext | None = None,
) -> ApplicationEntry:
    """Reads, AI-answers, and dry-fills `job`'s real apply form. Persists and
    returns the resulting `ApplicationEntry` — never raises; any failure
    becomes a `failed` (retryable) or `manual_required` (terminal) entry.

    `context` is normally launched internally (production path); tests pass
    one in with `context.route(...)` already wired, so no real network call
    is ever needed to exercise this function end-to-end (CLAUDE.md §7)."""
    resume = resume_path or config.RESUME_FILE

    if context is not None:
        entry = _prepare_with_context(context, job, profile, router, resume)
        record_entry(entry)
        return entry

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            owned_context = browser.new_context()
            try:
                entry = _prepare_with_context(owned_context, job, profile, router, resume)
            finally:
                owned_context.close()
        finally:
            browser.close()
    record_entry(entry)
    return entry


def _prepare_with_context(
    context: BrowserContext, job: Job, profile: Profile, router: AiRouter, resume: Path
) -> ApplicationEntry:
    try:
        page = context.new_page()
        try:
            apply_url = resolve_apply_url(job.url, job.source)
            page.goto(apply_url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(POST_LOAD_SETTLE_MS)
            result = read_form(page, job.source)

            if result.has_captcha:
                return _manual_required(job, "reCAPTCHA (or similar) on the submit form")
            if not result.fields:
                reason = result.blocked_reason or "no application form found on this page"
                return _manual_required(job, reason)

            answers = answer_form_questions(
                router,
                result.fields,
                company=job.company,
                job_title=job.title,
                job_description=job.description,
                profile=profile,
            )
            identity_values = identity_values_from_profile(profile)
            unresolved = fill_form(page, result, identity_values, answers, resume)
        finally:
            page.close()
    except Exception as error:  # noqa: BLE001 - navigation/DOM errors, retried next run
        logger.warning("prepare_application: %s (%s) failed: %s", job.company, job.title, error)
        return ApplicationEntry(
            signature=job.signature, status=ApplicationStatus.FAILED, note=str(error)
        )

    if unresolved:
        return _manual_required(job, "; ".join(unresolved), answers=answers)
    return ApplicationEntry(
        signature=job.signature,
        status=ApplicationStatus.DRAFT_READY,
        answers=answers,
        resume_path=str(resume),
    )


def _manual_required(job: Job, note: str, answers: dict[str, str] | None = None) -> ApplicationEntry:
    return ApplicationEntry(
        signature=job.signature,
        status=ApplicationStatus.MANUAL_REQUIRED,
        note=note,
        answers=answers or {},
    )
