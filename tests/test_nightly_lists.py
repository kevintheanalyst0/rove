"""Review lists for the nightly run (EATP-037): skipped vacancies and pending
questions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rove import config
from rove.nightly import questions, skipped
from rove.nightly.questions import VacancyRef
from rove.nightly.skipped import SkipReason, SkipStatus


@pytest.fixture(autouse=True)
def _isolated_files(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "NIGHTLY_SKIPPED_FILE", tmp_path / "skipped.jsonl")
    monkeypatch.setattr(config, "NIGHTLY_QUESTIONS_FILE", tmp_path / "questions.jsonl")
    monkeypatch.setattr(config, "NIGHTLY_LEARNED_ANSWERS_FILE", tmp_path / "learned.jsonl")


URL_A = "https://www.occ.com.mx/empleo/oferta/1/"
URL_B = "https://mx.computrabajo.com/oferta/2"


# ---------------------------------------------------------------- skipped ---


def test_no_file_yet_reads_as_empty():
    assert skipped.list_open() == []
    assert questions.list_open() == []


def test_record_and_list_a_skipped_vacancy():
    entry = skipped.record(URL_A, SkipReason.GOVERNMENT_ID, title="Analista Sr. de BI", company="MAXIMSLLC", source="occ")
    open_entries = skipped.list_open()
    assert [e.id for e in open_entries] == [entry.id]
    assert open_entries[0].reason == SkipReason.GOVERNMENT_ID
    assert open_entries[0].status == SkipStatus.OPEN


def test_same_url_skipped_twice_is_one_entry():
    skipped.record(URL_A, SkipReason.CAPTCHA)
    skipped.record(URL_A, SkipReason.CAPTCHA, note="again")
    assert len(skipped.list_open()) == 1


def test_resolve_removes_it_from_the_open_list():
    entry = skipped.record(URL_A, SkipReason.ACCOUNT_REQUIRED)
    done = skipped.resolve(entry.id)
    assert done is not None and done.status == SkipStatus.DONE and done.resolved_at is not None
    assert skipped.list_open() == []


def test_resolve_unknown_id_returns_none():
    assert skipped.resolve("nope") is None


def test_skipping_again_after_done_reopens_it():
    entry = skipped.record(URL_A, SkipReason.CAPTCHA)
    skipped.resolve(entry.id)
    skipped.record(URL_A, SkipReason.CAPTCHA)
    assert len(skipped.list_open()) == 1


def test_open_list_is_newest_first():
    skipped.record(URL_A, SkipReason.CAPTCHA)
    skipped.record(URL_B, SkipReason.OFFER_GONE)
    assert [e.url for e in skipped.list_open()] == [URL_B, URL_A]


@pytest.mark.parametrize(
    "bad_url",
    ["javascript:alert(1)", "data:text/html,<script>1</script>", "ftp://x.com/a", "//evil.com", "not a url", ""],
)
def test_non_http_urls_are_rejected(bad_url):
    with pytest.raises(ValidationError):
        skipped.record(bad_url, SkipReason.OTHER)
    assert skipped.list_open() == []


def test_corrupt_trailing_line_is_ignored():
    skipped.record(URL_A, SkipReason.CAPTCHA)
    with config.NIGHTLY_SKIPPED_FILE.open("ab") as handle:
        handle.write(b'{"id": "broken"')
    assert len(skipped.list_open()) == 1


# -------------------------------------------------------------- questions ---


def _vac(url, title="Vacante"):
    return VacancyRef(url=url, title=title, company="Acme")


def test_record_a_question():
    entry = questions.record("¿Qué plataformas de e-commerce has manejado?", "es", _vac(URL_A))
    assert [q.id for q in questions.list_open()] == [entry.id]


def test_same_question_with_different_case_and_punctuation_is_one_card_with_both_vacancies():
    questions.record("¿Qué plataformas de e-commerce has manejado?", "es", _vac(URL_A))
    questions.record("  qué plataformas de e-commerce has manejado  ", "es", _vac(URL_B))
    open_q = questions.list_open()
    assert len(open_q) == 1
    assert {v.url for v in open_q[0].vacancies} == {URL_A, URL_B}


def test_same_vacancy_twice_is_not_duplicated():
    questions.record("Pregunta", "es", _vac(URL_A))
    questions.record("Pregunta", "es", _vac(URL_A))
    assert len(questions.list_open()[0].vacancies) == 1


def test_same_text_in_another_language_is_a_different_card():
    questions.record("Salary expectation", "en", _vac(URL_A))
    questions.record("Salary expectation", "es", _vac(URL_B))
    assert len(questions.list_open()) == 2


def test_invalid_language_is_rejected():
    with pytest.raises(ValidationError):
        questions.PendingQuestion(id="x", question="q", language="fr")


def test_answer_saves_on_the_card_and_in_learned_answers():
    entry = questions.record("¿Cuentas con experiencia con Looker Studio?", "es", _vac(URL_A))
    done = questions.answer(entry.id, "  No.  ")
    assert done is not None and done.answer == "No."
    assert questions.list_open() == []
    assert questions.learned_answer_for("cuentas con experiencia con looker studio", "es") == "No."


def test_answer_unknown_id_returns_none():
    assert questions.answer("nope", "x") is None
    assert not config.NIGHTLY_LEARNED_ANSWERS_FILE.exists()


def test_an_answered_question_is_never_silently_reopened():
    entry = questions.record("Pregunta", "es", _vac(URL_A))
    questions.answer(entry.id, "Respuesta")
    again = questions.record("Pregunta", "es", _vac(URL_B))
    assert again.status == questions.QuestionStatus.ANSWERED
    assert questions.list_open() == []


def test_learned_answer_most_recent_wins_and_language_must_match():
    entry = questions.record("Pregunta", "es", _vac(URL_A))
    questions.answer(entry.id, "Primera")
    questions.answer(entry.id, "Segunda")
    assert questions.learned_answer_for("Pregunta", "es") == "Segunda"
    assert questions.learned_answer_for("Pregunta", "en") is None
    assert questions.learned_answer_for("Otra", "es") is None


def test_vacancies_to_retry_are_those_waiting_on_answered_questions_deduped():
    q1 = questions.record("P1", "es", _vac(URL_A))
    questions.record("P1", "es", _vac(URL_B))
    questions.record("P2", "es", _vac("https://example.com/open-one"))
    questions.answer(q1.id, "ok")
    assert {v.url for v in questions.vacancies_to_retry()} == {URL_A, URL_B}


def test_overlong_answer_is_rejected_by_the_model():
    entry = questions.record("Pregunta", "es", _vac(URL_A))
    with pytest.raises(ValidationError):
        questions.answer(entry.id, "x" * 2001)
