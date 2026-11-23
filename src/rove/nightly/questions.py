"""Questions the nightly runner could not answer from the CV or Kevin's
approved answers (EATP-037).

The runner never invents an answer: it records the question here, skips the
vacancy, and Kevin answers from his phone. His answer is then kept in
`learned_answers.jsonl` so the next run can reuse it. Same append-only,
latest-wins discipline as the other stores; the id comes from the normalized
question text + language, so the same question asked by ten vacancies is one
card with ten vacancies attached.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from rove import config
from rove.storage import append_jsonl, read_jsonl


class QuestionStatus(str, Enum):
    OPEN = "open"
    ANSWERED = "answered"


class VacancyRef(BaseModel):
    url: str = Field(max_length=2000)
    title: str = Field(default="", max_length=300)
    company: str = Field(default="", max_length=300)

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("url must be an absolute http(s) URL")
        return value


class PendingQuestion(BaseModel):
    id: str
    question: str = Field(max_length=1000)
    language: str = Field(default="es", pattern="^(es|en)$")
    vacancies: list[VacancyRef] = Field(default_factory=list, max_length=200)
    status: QuestionStatus = QuestionStatus.OPEN
    answer: str | None = Field(default=None, max_length=2000)
    asked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    answered_at: datetime | None = None


def normalize(question: str) -> str:
    """Case, spacing and trailing punctuation must not split one question in two."""
    text = re.sub(r"\s+", " ", question.strip().casefold())
    return text.strip(" ?¿:*.!¡")


def make_id(question: str, language: str) -> str:
    return hashlib.sha1(f"{language}|{normalize(question)}".encode()).hexdigest()[:12]


def latest() -> dict[str, PendingQuestion]:
    entries: dict[str, PendingQuestion] = {}
    for raw in read_jsonl(config.NIGHTLY_QUESTIONS_FILE):
        try:
            entry = PendingQuestion(**raw)
        except (TypeError, ValueError):
            continue
        entries[entry.id] = entry
    return entries


def record(question: str, language: str, vacancy: VacancyRef) -> PendingQuestion:
    """Register a question the runner could not answer.

    Already answered -> returned as is (the caller should have used the learned
    answer; it is never silently reopened). Already open -> the vacancy is added
    to the existing card (once per URL).
    """
    qid = make_id(question, language)
    existing = latest().get(qid)
    if existing is not None and existing.status == QuestionStatus.ANSWERED:
        return existing
    if existing is None:
        entry = PendingQuestion(id=qid, question=question.strip(), language=language, vacancies=[vacancy])
    elif any(v.url == vacancy.url for v in existing.vacancies):
        return existing
    else:
        # Re-validate (model_copy would skip the size limits).
        entry = PendingQuestion.model_validate(
            {**existing.model_dump(), "vacancies": [*existing.vacancies, vacancy]}
        )
    append_jsonl(config.NIGHTLY_QUESTIONS_FILE, entry.model_dump(mode="json"))
    return entry


def list_open() -> list[PendingQuestion]:
    open_entries = [e for e in latest().values() if e.status == QuestionStatus.OPEN]
    return sorted(open_entries, key=lambda e: e.asked_at, reverse=True)


def answer(question_id: str, text: str) -> PendingQuestion | None:
    """Kevin's answer. Saved on the card and in the learned-answers file.
    `None` if the id is unknown."""
    current = latest().get(question_id)
    if current is None:
        return None
    # Re-validate (model_copy would skip the length limit on the answer).
    done = PendingQuestion.model_validate(
        {
            **current.model_dump(),
            "status": QuestionStatus.ANSWERED,
            "answer": text.strip(),
            "answered_at": datetime.now(UTC),
        }
    )
    append_jsonl(config.NIGHTLY_QUESTIONS_FILE, done.model_dump(mode="json"))
    append_jsonl(
        config.NIGHTLY_LEARNED_ANSWERS_FILE,
        {
            "question": current.question,
            "normalized": normalize(current.question),
            "language": current.language,
            "answer": done.answer,
            "learned_at": done.answered_at.isoformat() if done.answered_at else None,
        },
    )
    return done


def learned_answer_for(question: str, language: str) -> str | None:
    """The most recent answer Kevin gave to this question, if any."""
    wanted = normalize(question)
    found: str | None = None
    for raw in read_jsonl(config.NIGHTLY_LEARNED_ANSWERS_FILE):
        if raw.get("language") == language and raw.get("normalized") == wanted and raw.get("answer"):
            found = raw["answer"]
    return found


def vacancies_to_retry() -> list[VacancyRef]:
    """Vacancies waiting on a question Kevin has since answered (deduped by URL)."""
    seen: dict[str, VacancyRef] = {}
    for entry in latest().values():
        if entry.status == QuestionStatus.ANSWERED:
            for vacancy in entry.vacancies:
                seen.setdefault(vacancy.url, vacancy)
    return list(seen.values())
