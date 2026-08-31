"""Tests for actually sending a prepared application (EATP-034, ADR-011).

Same route-interception discipline as `test_apply_prepare.py` — a real
Playwright `BrowserContext`, fixture HTML, never a live network call.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from rove import config
from rove.apply import store
from rove.apply.store import ApplicationEntry, ApplicationStatus
from rove.apply.submit import submit_application
from rove.models import Job
from rove.profile import load_profile

PROFILE = load_profile()


# Real Greenhouse/Lever forms are JS-driven (fetch/XHR on submit, not a
# native GET/POST — their real inputs have no `name` attribute at all, only
# `id`, confirmed live in browser.py's own probe). This fixture uses a
# native `method="get"` form purely so the test can observe what was
# actually submitted via the resulting query string — a detection
# convenience, not a claim about how the real boards transport data.
# `submit_form`'s own success check (URL change to thanks/confirm, or a
# "thank you" / "successfully submitted" text) is written to catch either a
# real navigation or a SPA's client-side state change; only a real (and
# genuinely irreversible) live submission could fully confirm it against an
# actual board, which was deliberately not attempted here.
FORM_WITH_REDIRECT_HTML = """
<html><body><form id="application_form" action="https://fixture.test/thanks" method="get">
  <input type="text" id="first_name" name="first_name" required>
  <input type="text" id="last_name" name="last_name" required>
  <input type="text" id="email" name="email" required>
  <label for="question_1">Why do you want this role?</label>
  <input type="text" id="question_1" name="question_1" required>
  <button type="submit">Submit</button>
</form></body></html>
"""
THANKS_HTML = "<html><body><h1>Thank you for applying!</h1></body></html>"
NO_FORM_HTML = "<html><body><p>nothing here</p></body></html>"


@pytest.fixture(autouse=True)
def _isolated_applications_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _routed_context(browser, *, form_html: str | None, fail: bool = False):
    context = browser.new_context()

    def handler(route):
        if fail:
            route.abort()
            return
        url = route.request.url
        if "/thanks" in url:
            route.fulfill(body=THANKS_HTML, content_type="text/html")
        else:
            route.fulfill(body=form_html, content_type="text/html")

    context.route("**/*", handler)
    return context


def _job() -> Job:
    return Job(
        source="greenhouse",
        source_job_id="123",
        title="Senior People Analytics Analyst",
        company="GitLab",
        description="Analyze people data across the org.",
        url="https://fixture.test/gitlab-job",
    )


def _draft_entry(signature: str) -> ApplicationEntry:
    return ApplicationEntry(
        signature=signature,
        status=ApplicationStatus.DRAFT_READY,
        answers={"Why do you want this role?": "Because I love people analytics."},
    )


def test_submit_succeeds_and_marks_the_entry_submitted(browser):
    job = _job()
    entry = _draft_entry(job.signature)
    context = _routed_context(browser, form_html=FORM_WITH_REDIRECT_HTML)

    updated = submit_application(job, PROFILE, entry, context=context)
    context.close()

    assert updated.status == ApplicationStatus.SUBMITTED
    assert store.latest_entries()[job.signature].status == ApplicationStatus.SUBMITTED


def test_submit_reuses_the_stored_answers_without_asking_ai_again(browser):
    """`submit_application` takes no `AiRouter` at all (see its signature) —
    this proves the *value* actually submitted is exactly what was stored on
    the entry, not something freshly derived. The redirect target is a GET,
    so the submitted field value shows up in its own query string — no need
    to reach into Playwright's page object to observe it."""
    job = _job()
    entry = _draft_entry(job.signature)
    seen_urls: list[str] = []

    context = browser.new_context()

    def handler(route):
        seen_urls.append(route.request.url)
        if "/thanks" in route.request.url:
            route.fulfill(body=THANKS_HTML, content_type="text/html")
        else:
            route.fulfill(body=FORM_WITH_REDIRECT_HTML, content_type="text/html")

    context.route("**/*", handler)

    submit_application(job, PROFILE, entry, context=context)
    context.close()

    thanks_requests = [u for u in seen_urls if "/thanks" in u]
    assert thanks_requests
    assert "love+people+analytics" in thanks_requests[0] or "love%20people%20analytics" in thanks_requests[0]


def test_submit_marks_failed_when_a_required_field_cannot_be_filled(browser):
    job = _job()
    entry = ApplicationEntry(signature=job.signature, status=ApplicationStatus.DRAFT_READY, answers={})
    context = _routed_context(browser, form_html=FORM_WITH_REDIRECT_HTML)

    updated = submit_application(job, PROFILE, entry, context=context)
    context.close()

    assert updated.status == ApplicationStatus.FAILED
    assert "why do you want this role" in (updated.note or "").lower()


def test_submit_marks_manual_required_when_the_form_disappeared(browser):
    job = _job()
    entry = _draft_entry(job.signature)
    context = _routed_context(browser, form_html=NO_FORM_HTML)

    updated = submit_application(job, PROFILE, entry, context=context)
    context.close()

    assert updated.status == ApplicationStatus.MANUAL_REQUIRED


def test_submit_marks_failed_on_navigation_error(browser):
    job = _job()
    entry = _draft_entry(job.signature)
    context = _routed_context(browser, form_html=FORM_WITH_REDIRECT_HTML, fail=True)

    updated = submit_application(job, PROFILE, entry, context=context)
    context.close()

    assert updated.status == ApplicationStatus.FAILED
