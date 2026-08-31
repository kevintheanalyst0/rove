"""Headless-browser apply-form reading and filling (EATP-034, ADR-011).

Real-world shape, captured 2026-08-30 against live boards (GitLab/Greenhouse,
Coinbase/Greenhouse-embed, Palantir/Lever) — see
`docs/adr/ADR-011-auto-apply-draft-and-sweep.md` for why a browser was chosen
over raw HTTP form replay.

**Greenhouse** (`job-boards.greenhouse.io` hosted boards): the apply form is
on the job listing page itself (`job.url` unchanged). Standard fields use
fixed ids (`first_name`, `last_name`, `email`, `phone`, `resume`,
`cover_letter`). A fixed EEO block (`gender`, `hispanic_ethnicity`,
`veteran_status`, `disability_status`) always renders as a React-Select
combobox with one option whose text contains a decline/no-answer phrase
("Decline To Self Identify", "I don't wish to answer", ...) — clicking the
input opens `#react-select-<id>-listbox`, and that decline option is what
this module always picks (ADR-011 §6). Everything else is a custom
`question_<id>` field whose real text lives in `<label for="question_<id>">`
— including fields you'd expect to be standard, like "LinkedIn Profile" on
GitLab's board (confirms why a fixed Q&A bank wouldn't have worked). Many
boards protect submission with a Google reCAPTCHA
(`textarea[name=g-recaptcha-response]`) — detected here, but never fought;
a job with one is always `manual_required`.

**Greenhouse custom-domain embeds are a real, deliberate boundary, not an
unfinished feature.** Live-verified (2026-08-30): `coinbase.com/careers/
positions/...?gh_jid=...` serves a Cloudflare "Just a moment..." bot
challenge, not a slow-loading embed — the same class of block that got
Indeed removed entirely in EATP-033 and Glassdoor never attempted in
EATP-030. Fighting a Cloudflare challenge unattended isn't a code problem to
solve; `read_form` detects this specific page shape (`blocked_reason` below)
so the resulting `manual_required` entry says *why* instead of looking like
a silent failure.

**Lever** (`jobs.lever.co`): the job listing page has NO form — the real one
is at `<hostedUrl>/apply` (`resolve_apply_url` below). Standard fields:
`name`, `email`, `phone`, `location`, `resume` (file), and genuinely
standard `urls[LinkedIn]` / `urls[GitHub]` / `urls[Portfolio]` fields. Custom
questions render as "additional info cards" — each card is a hidden
`input[name="cards[<card-id>][baseTemplate]"]` whose value is a full JSON
spec: `{text, fields: [{type, text, required, options?}, ...]}`. Each
`fields[i]` maps to a real form control at `cards[<card-id>][field<i>]`:
`text`/`textarea` → a plain input; `multiple-choice` → radios (pick one);
`multiple-select` → checkboxes (pick one or more); `dropdown` → a real
`<select>`. All confirmed live against Palantir's board, including one
`dropdown` with 3301 options ("which university...") — a genuinely
unreasonable number of options to hand an AI prompt, so any choice-type
field with more than `MAX_CHOICE_OPTIONS` options is deliberately left
`unsupported` rather than blowing the AI-quota budget on one field
(CLAUDE.md §7); everything else is fully handled.
"""

from __future__ import annotations

import html as html_module
import json
from enum import Enum
from pathlib import Path

from playwright.sync_api import Page
from pydantic import BaseModel

from rove.profile import Profile

MAX_CHOICE_OPTIONS = 100

DECLINE_KEYWORDS = ("decline", "wish to answer", "want to answer", "prefer not")

GREENHOUSE_IDENTITY_SELECTORS: dict[str, str] = {
    "#first_name": "first_name",
    "#last_name": "last_name",
    "#email": "email",
    "#phone": "phone",
    "#resume": "resume",
    "#cover_letter": "cover_letter",
}
GREENHOUSE_EEO_IDS = ("gender", "hispanic_ethnicity", "veteran_status", "disability_status")

LEVER_IDENTITY_SELECTORS: dict[str, str] = {
    "input[name='name']": "name",
    "input[name='email']": "email",
    "input[name='phone']": "phone",
    "input[name='location']": "location",
    "input[name='urls[LinkedIn]']": "linkedin_url",
    "input[name='urls[GitHub]']": "github_url",
    "input[name='urls[Portfolio]']": "portfolio_url",
    "input[name='resume']": "resume",
}


class FieldKind(str, Enum):
    IDENTITY = "identity"
    EEO_DECLINE = "eeo_decline"
    CUSTOM = "custom"
    UNSUPPORTED = "unsupported"


class FormField(BaseModel):
    selector: str
    kind: FieldKind
    label: str
    required: bool = False
    profile_key: str | None = None
    options: list[str] = []
    multi: bool = False
    control: str = "text"  # "text" | "radio" | "checkbox" | "select"


class FormReadResult(BaseModel):
    fields: list[FormField]
    has_captcha: bool
    submit_selector: str | None
    blocked_reason: str | None = None


def resolve_apply_url(job_url: str, source: str) -> str:
    """Lever's real form lives at `<hostedUrl>/apply`; Greenhouse's job page
    IS the apply page for the common (job-boards.greenhouse.io) case."""
    if source == "lever":
        return job_url.rstrip("/") + "/apply"
    return job_url


def _detect_bot_challenge(page: Page) -> str | None:
    """Cloudflare (and similar) bot-challenge interstitials never render the
    real form — live-verified against a real custom-domain Greenhouse embed
    (coinbase.com). Distinguished from "no form on this page" so a
    `manual_required` entry can say *why* rather than looking like a bug."""
    title = (page.title() or "").lower()
    if "just a moment" in title or page.query_selector("#challenge-error-text") is not None:
        return "bot-protection challenge page (Cloudflare or similar) — not automatable"
    return None


def read_form(page: Page, source: str) -> FormReadResult:
    """Classifies every relevant field on the already-loaded `page`. Returns
    `fields=[]` when no recognizable form was found — `blocked_reason` is set
    when that's specifically a bot-challenge page, so the caller can tell
    "nothing to automate here" apart from "something actively blocked us"."""
    if page.query_selector("form") is None:
        return FormReadResult(
            fields=[],
            has_captcha=False,
            submit_selector=None,
            blocked_reason=_detect_bot_challenge(page),
        )

    has_captcha = page.query_selector("textarea[name='g-recaptcha-response']") is not None
    fields: list[FormField] = []

    identity_selectors = (
        GREENHOUSE_IDENTITY_SELECTORS if source == "greenhouse" else LEVER_IDENTITY_SELECTORS
    )
    for selector, profile_key in identity_selectors.items():
        el = page.query_selector(selector)
        if el is None:
            continue
        fields.append(
            FormField(
                selector=selector,
                kind=FieldKind.IDENTITY,
                label=profile_key,
                required=el.get_attribute("required") is not None,
                profile_key=profile_key,
            )
        )

    if source == "greenhouse":
        for field_id in GREENHOUSE_EEO_IDS:
            if page.query_selector(f"#{field_id}") is not None:
                fields.append(
                    FormField(selector=f"#{field_id}", kind=FieldKind.EEO_DECLINE, label=field_id)
                )
        for el in page.query_selector_all("input[id^='question_'], textarea[id^='question_']"):
            field_id = el.get_attribute("id") or ""
            label_el = page.query_selector(f"label[for='{field_id}']")
            label = (label_el.inner_text() if label_el else field_id).strip().rstrip("*").strip()
            fields.append(
                FormField(
                    selector=f"#{field_id}",
                    kind=FieldKind.CUSTOM,
                    label=label,
                    required=el.get_attribute("required") is not None,
                )
            )
    else:  # lever
        fields.extend(_read_lever_cards(page))

    submit_el = page.query_selector("button[type='submit'], input[type='submit']")
    submit_selector = None
    if submit_el is not None:
        submit_selector = "button[type='submit'], input[type='submit']"

    return FormReadResult(fields=fields, has_captcha=has_captcha, submit_selector=submit_selector)


def _read_lever_cards(page: Page) -> list[FormField]:
    """Parses every `cards[<id>][baseTemplate]` hidden JSON spec into real
    `FormField`s. Live-verified field-spec shape (`type`/`text`/`required`/
    `options`) against Palantir's board — see module docstring."""
    fields: list[FormField] = []
    for hidden in page.query_selector_all("input[name$='[baseTemplate]']"):
        name = hidden.get_attribute("name") or ""
        card_id = name.split("[", 2)[1].rstrip("]") if "[" in name else None
        if not card_id:
            continue
        raw_value = hidden.get_attribute("value") or ""
        try:
            spec = json.loads(html_module.unescape(raw_value))
        except (json.JSONDecodeError, TypeError):
            continue

        for index, question in enumerate(spec.get("fields", [])):
            q_type = question.get("type")
            label = question.get("text", "")
            required = bool(question.get("required", False))
            selector = f"[name='cards[{card_id}][field{index}]']"
            options = [opt.get("text", "") for opt in question.get("options") or []]

            if q_type in ("text", "textarea"):
                fields.append(
                    FormField(selector=selector, kind=FieldKind.CUSTOM, label=label, required=required)
                )
            elif q_type == "multiple-choice" and len(options) <= MAX_CHOICE_OPTIONS:
                fields.append(
                    FormField(
                        selector=selector, kind=FieldKind.CUSTOM, label=label, required=required,
                        options=options, control="radio",
                    )
                )
            elif q_type == "multiple-select" and len(options) <= MAX_CHOICE_OPTIONS:
                fields.append(
                    FormField(
                        selector=selector, kind=FieldKind.CUSTOM, label=label, required=required,
                        options=options, multi=True, control="checkbox",
                    )
                )
            elif q_type == "dropdown" and len(options) <= MAX_CHOICE_OPTIONS:
                fields.append(
                    FormField(
                        selector=selector, kind=FieldKind.CUSTOM, label=label, required=required,
                        options=options, control="select",
                    )
                )
            else:
                # either an unrecognized type, or a choice field with more
                # options than MAX_CHOICE_OPTIONS (e.g. a 3301-option
                # university dropdown) — too costly to hand an AI prompt,
                # deliberately unsupported rather than guessed at.
                fields.append(FormField(selector=selector, kind=FieldKind.UNSUPPORTED, label=label, required=required))
    return fields


def _select_decline_option(page: Page, field_selector: str) -> bool:
    field_id = field_selector.lstrip("#")
    page.click(field_selector)
    page.wait_for_timeout(300)
    options = page.query_selector_all(f"#react-select-{field_id}-listbox [role='option']")
    for option in options:
        text = (option.inner_text() or "").lower()
        if any(keyword in text for keyword in DECLINE_KEYWORDS):
            option.click()
            return True
    page.keyboard.press("Escape")
    return False


def fill_form(
    page: Page,
    result: FormReadResult,
    identity_values: dict[str, str],
    answers: dict[str, str],
    resume_path: Path | None,
) -> list[str]:
    """Fills every field it knows how to. Returns a list of human-readable
    reasons for each REQUIRED field it couldn't fill — an empty list means
    the form is genuinely ready to submit."""
    unresolved: list[str] = []

    for field in result.fields:
        if field.kind == FieldKind.IDENTITY:
            if field.profile_key in ("resume", "cover_letter"):
                if field.profile_key == "resume" and resume_path and resume_path.exists():
                    page.set_input_files(field.selector, str(resume_path))
                elif field.required:
                    unresolved.append(f"{field.label}: no resume file available")
                continue
            value = identity_values.get(field.profile_key or "", "")
            if value:
                page.fill(field.selector, value)
            elif field.required:
                unresolved.append(f"{field.label}: no profile value for this field")

        elif field.kind == FieldKind.EEO_DECLINE:
            if not _select_decline_option(page, field.selector):
                unresolved.append(f"{field.label}: no decline-style option found")

        elif field.kind == FieldKind.CUSTOM:
            answer = answers.get(field.label)
            if not answer:
                if field.required:
                    unresolved.append(f"{field.label}: no AI answer available")
                continue
            if field.control == "select":
                page.select_option(field.selector, label=answer)
            elif field.control in ("radio", "checkbox"):
                chosen = [answer] if not field.multi else [v.strip() for v in answer.split(";")]
                missing = [v for v in chosen if v not in field.options]
                if missing:
                    unresolved.append(f"{field.label}: AI answer not among the offered options ({missing})")
                    continue
                for value in chosen:
                    page.check(f"{field.selector}[value='{value}']")
            else:
                page.fill(field.selector, answer)

        elif field.kind == FieldKind.UNSUPPORTED and field.required:
            unresolved.append(f"{field.label}: unsupported field type (not automated in v1)")

    return unresolved


def identity_values_from_profile(profile: Profile) -> dict[str, str]:
    """Maps `Profile` (+ its `[application]` table) to every deterministic
    identity key used by `GREENHOUSE_IDENTITY_SELECTORS`/
    `LEVER_IDENTITY_SELECTORS` above. Shared by `apply/prepare.py` and
    `apply/submit.py` so both fill the exact same values."""
    first_name, _, last_name = profile.name.partition(" ")
    app = profile.application
    return {
        "first_name": first_name,
        "last_name": last_name,
        "name": profile.name,
        "email": app.email,
        "phone": app.phone,
        "location": profile.location,
        "linkedin_url": app.linkedin_url,
        "github_url": app.github_url,
        "portfolio_url": app.portfolio_url,
    }


def submit_form(page: Page, result: FormReadResult, timeout_ms: int = 15000) -> bool:
    """Clicks submit and waits for a success signal. Never call this when
    `result.has_captcha` is true — the click will just fail silently against
    an unsolved challenge; that case must already be `manual_required` before
    this function is reached."""
    if result.submit_selector is None:
        return False
    page.click(result.submit_selector)
    try:
        page.wait_for_url(lambda url: "thanks" in url.lower() or "confirm" in url.lower(), timeout=timeout_ms)
        return True
    except Exception:  # noqa: BLE001 - no URL change yet; fall back to a text check
        return (
            page.query_selector("text=/thank you/i") is not None
            or page.query_selector("text=/successfully submitted/i") is not None
        )
