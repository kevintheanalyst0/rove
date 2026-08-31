"""Tests for the auto-apply draft orchestration (EATP-034, ADR-011).

Exercises `prepare_application` end-to-end against a real (injected)
Playwright `BrowserContext` with `context.route(...)` serving fixture HTML —
never a live network call (CLAUDE.md §7's testing discipline, extended to
browser automation). The AI side is a mocked `Provider`, same as
`test_apply_questions.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from rove import config
from rove.ai.base import Provider
from rove.ai.router import AiRouter
from rove.ai.usage import UsageTracker
from rove.apply import store
from rove.apply.prepare import is_eligible, prepare_application
from rove.apply.store import ApplicationStatus
from rove.models import Grade, Job, ScoredJob
from rove.profile import load_profile

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PROFILE = load_profile()

NO_FORM_HTML = "<html><head><title>GitLab Careers</title></head><body><p>hi</p></body></html>"
CLOUDFLARE_HTML = (
    '<html><head><title>Just a moment...</title></head>'
    '<body><div id="challenge-error-text"></div></body></html>'
)
SIMPLE_FORM_HTML = """
<html><body><form id="application_form">
  <input type="text" id="first_name" required>
  <input type="text" id="last_name" required>
  <input type="text" id="email" required>
  <input type="file" id="resume" required>
  <label for="question_1">Why do you want this role?</label>
  <input type="text" id="question_1" required>
  <button type="submit">Submit</button>
</form></body></html>
"""


@pytest.fixture(autouse=True)
def _isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")
    monkeypatch.setattr(config, "AI_USAGE_FILE", tmp_path / "ai_usage.json")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _routed_context(browser, html: str, *, fail: bool = False):
    context = browser.new_context()

    def handler(route):
        if fail:
            route.abort()
        else:
            route.fulfill(body=html, content_type="text/html")

    context.route("**/*", handler)
    return context


class MockQuestionProvider(Provider):
    def __init__(self, response_text: str) -> None:
        self.id = "mock"
        self._response_text = response_text

    @property
    def configured(self) -> bool:
        return True

    def evaluate_batch(self, jobs, profile):
        raise NotImplementedError

    def answer_questions(self, prompt: str) -> str:
        return self._response_text


def _router(response_text: str = '{"answers": []}') -> AiRouter:
    provider = MockQuestionProvider(response_text)
    return AiRouter({"mock": provider}, order=["mock"], usage=UsageTracker())


def _job(**overrides) -> Job:
    defaults = {
        "source": "greenhouse",
        "source_job_id": "123",
        "title": "Senior People Analytics Analyst",
        "company": "GitLab",
        "description": "Analyze people data across the org.",
        "url": "https://fixture.test/gitlab-job",
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_is_eligible_true_for_greenhouse_lever_non_d_grades():
    # prefilter_score=75 -> Grade.B per the canonical score->grade mapping
    # (DATA-CONTRACTS.md); `grade` is re-derived by ScoredJob's own
    # validator, never trusted as passed in.
    scored = ScoredJob(job=_job(source="greenhouse"), prefilter_score=75, prefilter_passed=True)
    assert scored.grade == Grade.B
    assert is_eligible(scored) is True


def test_is_eligible_false_for_grade_d():
    scored = ScoredJob(job=_job(source="greenhouse"), prefilter_score=20, prefilter_passed=False)
    assert scored.grade == Grade.D
    assert is_eligible(scored) is False


def test_is_eligible_false_for_other_sources():
    scored = ScoredJob(job=_job(source="occ"), prefilter_score=85, prefilter_passed=True)
    assert scored.grade == Grade.A
    assert is_eligible(scored) is False


def test_prepare_returns_manual_required_when_captcha_present(browser):
    html = (FIXTURES_DIR / "greenhouse_apply_gitlab.html").read_text()
    context = _routed_context(browser, html)
    entry = prepare_application(_job(), PROFILE, _router(), context=context)
    context.close()

    assert entry.status == ApplicationStatus.MANUAL_REQUIRED
    assert "recaptcha" in (entry.note or "").lower()
    # persisted
    assert store.latest_entries()[entry.signature].status == ApplicationStatus.MANUAL_REQUIRED


def test_prepare_returns_manual_required_when_no_form_found(browser):
    context = _routed_context(browser, NO_FORM_HTML)
    entry = prepare_application(_job(), PROFILE, _router(), context=context)
    context.close()

    assert entry.status == ApplicationStatus.MANUAL_REQUIRED
    assert "no application form" in (entry.note or "").lower()


def test_prepare_reports_the_cloudflare_block_reason(browser):
    context = _routed_context(browser, CLOUDFLARE_HTML)
    entry = prepare_application(_job(), PROFILE, _router(), context=context)
    context.close()

    assert entry.status == ApplicationStatus.MANUAL_REQUIRED
    assert "cloudflare" in (entry.note or "").lower() or "bot" in (entry.note or "").lower()


def test_prepare_returns_draft_ready_on_a_full_successful_fill(browser, tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 fake")

    response = json.dumps(
        {"answers": [{"id": "q0", "answer": "Because I love people analytics."}]}
    )
    context = _routed_context(browser, SIMPLE_FORM_HTML)

    entry = prepare_application(_job(), PROFILE, _router(response), resume_path=resume, context=context)
    context.close()

    assert entry.status == ApplicationStatus.DRAFT_READY
    assert entry.answers == {"Why do you want this role?": "Because I love people analytics."}
    assert entry.resume_path == str(resume)


def test_prepare_falls_back_to_manual_required_when_ai_gives_no_answer(browser):
    # every required custom question left unanswered -> can't be a real draft
    context = _routed_context(browser, SIMPLE_FORM_HTML)
    entry = prepare_application(_job(), PROFILE, _router('{"answers": []}'), context=context)
    context.close()

    assert entry.status == ApplicationStatus.MANUAL_REQUIRED
    assert "why do you want this role" in (entry.note or "").lower()


def test_prepare_returns_failed_on_navigation_error(browser):
    context = _routed_context(browser, SIMPLE_FORM_HTML, fail=True)
    entry = prepare_application(_job(), PROFILE, _router(), context=context)
    context.close()

    assert entry.status == ApplicationStatus.FAILED
