"""Tests for apply-form reading/filling (EATP-034) against recorded fixture
HTML — no live network, per CLAUDE.md §7's testing discipline extended to
browser automation (never depend on a real site being reachable/unchanged).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from rove.apply.browser import (
    MAX_CHOICE_OPTIONS,
    FieldKind,
    fill_form,
    read_form,
    resolve_apply_url,
    submit_form,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def greenhouse_page(browser):
    page = browser.new_page()
    page.set_content((FIXTURES_DIR / "greenhouse_apply_gitlab.html").read_text())
    yield page
    page.close()


def _lever_html(option_count: int) -> str:
    template = (FIXTURES_DIR / "lever_apply_palantir.html").read_text()
    options_json = ",".join(json.dumps({"text": f"Option {i}"}) for i in range(option_count))
    html_ = template.replace("REPLACED_AT_BUILD", options_json.replace('"', "&quot;"))
    select_options = "".join(f'<option value="Option {i}">Option {i}</option>' for i in range(option_count))
    return html_.replace("<!--SELECT_OPTIONS-->", select_options)


@pytest.fixture
def lever_page(browser):
    page = browser.new_page()
    # one option below the cap -> stays supported; separate test below covers "over the cap"
    page.set_content(_lever_html(MAX_CHOICE_OPTIONS - 1))
    yield page
    page.close()


def test_resolve_apply_url_appends_slash_apply_for_lever():
    assert (
        resolve_apply_url("https://jobs.lever.co/palantir/abc", "lever")
        == "https://jobs.lever.co/palantir/abc/apply"
    )


def test_resolve_apply_url_unchanged_for_greenhouse():
    url = "https://job-boards.greenhouse.io/gitlab/jobs/123"
    assert resolve_apply_url(url, "greenhouse") == url


def test_read_form_returns_empty_when_no_form_present(browser):
    page = browser.new_page()
    page.set_content("<html><body><p>no form here</p></body></html>")
    result = read_form(page, "greenhouse")
    page.close()

    assert result.fields == []
    assert result.has_captcha is False
    assert result.submit_selector is None
    assert result.blocked_reason is None


def test_read_form_detects_a_cloudflare_bot_challenge_page(browser):
    page = browser.new_page()
    page.set_content(
        '<html><head><title>Just a moment...</title></head>'
        '<body><div id="challenge-error-text"></div></body></html>'
    )
    result = read_form(page, "greenhouse")
    page.close()

    assert result.fields == []
    assert result.blocked_reason is not None
    assert "cloudflare" in result.blocked_reason.lower() or "bot" in result.blocked_reason.lower()


def test_read_form_classifies_greenhouse_fields(greenhouse_page):
    result = read_form(greenhouse_page, "greenhouse")
    by_kind = {}
    for field in result.fields:
        by_kind.setdefault(field.kind, []).append(field)

    assert {f.profile_key for f in by_kind[FieldKind.IDENTITY]} == {
        "first_name",
        "last_name",
        "email",
        "phone",
        "resume",
        "cover_letter",
    }
    assert {f.label for f in by_kind[FieldKind.EEO_DECLINE]} == {"gender", "veteran_status"}
    custom_labels = {f.label for f in by_kind[FieldKind.CUSTOM]}
    assert "LinkedIn Profile" in custom_labels
    assert any("sponsorship" in label.lower() for label in custom_labels)
    assert result.has_captcha is True


def test_read_form_classifies_lever_identity_and_card_fields(lever_page):
    result = read_form(lever_page, "lever")
    by_kind = {}
    for field in result.fields:
        by_kind.setdefault(field.kind, []).append(field)

    assert {f.profile_key for f in by_kind[FieldKind.IDENTITY]} == {
        "name",
        "email",
        "phone",
        "location",
        "linkedin_url",
        "github_url",
        "portfolio_url",
        "resume",
    }
    assert result.has_captcha is False

    custom = {f.label: f for f in by_kind[FieldKind.CUSTOM]}
    assert custom["Preferred Name"].control == "text"
    assert custom["Are you legally authorized to work in the country for which you are applying?"].control == "radio"
    assert custom["Are you legally authorized to work in the country for which you are applying?"].options == [
        "Yes",
        "No",
    ]
    assert custom["Language Skill(s) (Check all that apply)"].control == "checkbox"
    assert custom["Language Skill(s) (Check all that apply)"].multi is True
    # the (just-under-the-cap) university dropdown is supported here
    assert custom["Which university did you attend?"].control == "select"


def test_read_form_marks_an_oversized_dropdown_unsupported(browser):
    page = browser.new_page()
    page.set_content(_lever_html(MAX_CHOICE_OPTIONS + 1))
    result = read_form(page, "lever")
    page.close()

    by_label = {f.label: f for f in result.fields}
    assert by_label["Which university did you attend?"].kind == FieldKind.UNSUPPORTED


def test_fill_form_fills_identity_and_custom_fields(greenhouse_page):
    result = read_form(greenhouse_page, "greenhouse")
    identity_values = {
        "first_name": "Kevin",
        "last_name": "Castillo",
        "email": "castillok54@gmail.com",
        "phone": "+52 443 169 2514",
    }
    answers = {
        "LinkedIn Profile": "https://www.linkedin.com/in/kevin-castillo-844005244/",
        "Will you now or in the future require sponsorship for a visa to remain in your current location?": "No",
    }

    unresolved = fill_form(greenhouse_page, result, identity_values, answers, resume_path=None)

    assert greenhouse_page.input_value("#first_name") == "Kevin"
    assert greenhouse_page.input_value("#question_37171442002") == (
        "https://www.linkedin.com/in/kevin-castillo-844005244/"
    )
    # resume is required but no file was provided -> must be reported
    assert any("resume" in reason.lower() for reason in unresolved)


def test_fill_form_selects_the_decline_option_for_eeo_fields(greenhouse_page):
    result = read_form(greenhouse_page, "greenhouse")
    fill_form(greenhouse_page, result, {}, {}, resume_path=None)

    assert greenhouse_page.input_value("#gender") == "Decline To Self Identify"
    assert greenhouse_page.input_value("#veteran_status") == "I don't wish to answer"


def test_fill_form_handles_lever_radio_checkbox_and_select_cards(lever_page):
    result = read_form(lever_page, "lever")
    identity_values = {"name": "Kevin Castillo", "email": "castillok54@gmail.com"}
    answers = {
        "Preferred Name": "Kevin",
        "Are you legally authorized to work in the country for which you are applying?": "Yes",
        "Language Skill(s) (Check all that apply)": "English (ENG); Spanish (SPA)",
        "Which university did you attend?": "Option 3",
    }

    unresolved = fill_form(lever_page, result, identity_values, answers, resume_path=None)

    assert lever_page.is_checked("input[value='Yes'][name*='field1']")
    assert lever_page.is_checked("input[value='English (ENG)'][name*='field2']")
    assert lever_page.is_checked("input[value='Spanish (SPA)'][name*='field2']")
    assert lever_page.eval_on_selector("select[name*='field0']", "el => el.value") == "Option 3"
    # only the resume (required, no file) should be left unresolved
    assert len(unresolved) == 1
    assert "resume" in unresolved[0].lower()


def test_fill_form_flags_an_ai_answer_not_among_the_offered_options(lever_page):
    result = read_form(lever_page, "lever")
    answers = {
        "Are you legally authorized to work in the country for which you are applying?": "Maybe",
    }

    unresolved = fill_form(lever_page, result, {}, answers, resume_path=None)

    assert any("not among the offered options" in reason for reason in unresolved)


def test_submit_form_returns_false_with_no_submit_selector(greenhouse_page):
    result = read_form(greenhouse_page, "greenhouse")
    result = result.model_copy(update={"submit_selector": None})

    assert submit_form(greenhouse_page, result) is False
