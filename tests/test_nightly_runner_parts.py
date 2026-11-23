"""Selector, answers loader, outcome parsing and the Rove client for the nightly
runner (EATP-037 phase 2). No network, no AI: Rove is a `httpx.MockTransport`."""

from __future__ import annotations

import json

import httpx
import pytest

from rove.nightly import answers, outcomes, selector
from rove.nightly.client import RoveClient
from rove.nightly.selector import Candidate
from rove.nightly.skipped import SkipReason


def _item(sig, *, title="Analista de datos", company=None, source="occ", grade="B", score=70, days=1, url=None):
    return {
        "signature": sig,
        "scored": {
            "grade": grade,
            "final_score": score,
            "job": {"title": title, "company": company or f"Co {sig}", "source": source, "days_old": days,
                    "url": url or f"https://example.com/{sig}"},
        },
    }


def _inbox(*items):
    return {"buckets": {"hoy": list(items)}, "total": len(items)}


# --------------------------------------------------------------- selector ---


def test_only_supported_sources_and_min_grade():
    inbox = _inbox(
        _item("a", source="occ"), _item("b", source="computrabajo"), _item("c", source="greenhouse"),
        _item("d", source="weremoto"), _item("e", grade="D"), _item("f", grade="C"),
    )
    assert {c.signature for c in selector.candidates_from_inbox(inbox)} == {"a", "b", "f"}


@pytest.mark.parametrize(
    "title",
    ["Ejecutivo de Ventas Home Office", "Agente Call Center", "Customer Support Rep", "Auxiliar de Nómina",
     "Community Marketing Manager", "Reclutador IT", "Asesor Comercial", "Atención a clientes remoto"],
)
def test_excluded_categories_by_title(title):
    assert selector.candidates_from_inbox(_inbox(_item("x", title=title))) == []


def test_admin_data_and_procurement_titles_are_kept():
    inbox = _inbox(_item("a", title="Auxiliar Administrativo"), _item("b", title="Analista de Compras"),
                   _item("c", title="Capturista de datos"))
    assert len(selector.candidates_from_inbox(inbox)) == 3


def test_mass_posters_are_excluded_but_small_companies_are_not():
    spam = [_item(f"s{i}", company="Mega Jobs") for i in range(5)]
    ok = [_item("k1", company="Small Co"), _item("k2", company="Small Co")]
    result = selector.candidates_from_inbox(_inbox(*spam, *ok))
    assert {c.signature for c in result} == {"k1", "k2"}


def test_excluded_urls_are_skipped():
    inbox = _inbox(_item("a", url="https://x.com/a"), _item("b", url="https://x.com/b"))
    result = selector.candidates_from_inbox(inbox, exclude_urls={"https://x.com/a"})
    assert [c.signature for c in result] == ["b"]


def test_order_is_retries_first_then_score_then_freshness():
    inbox = _inbox(
        _item("low", score=60, url="https://x.com/low"),
        _item("high", score=90, url="https://x.com/high"),
        _item("retry", score=55, url="https://x.com/retry"),
        _item("high_old", score=90, days=9, url="https://x.com/high_old"),
    )
    order = [c.signature for c in selector.candidates_from_inbox(inbox, retry_urls=["https://x.com/retry"])]
    assert order == ["retry", "high", "high_old", "low"]


def test_empty_or_odd_inbox_is_fine():
    assert selector.candidates_from_inbox({}) == []
    assert selector.candidates_from_inbox({"buckets": {}}) == []


# ---------------------------------------------------------------- answers ---


def test_missing_or_broken_answers_file_is_empty(tmp_path):
    assert answers.load_applicant_answers(tmp_path / "nope.toml") == {}
    bad = tmp_path / "bad.toml"
    bad.write_text("not [valid", encoding="utf-8")
    assert answers.load_applicant_answers(bad) == {}


def test_render_includes_answers_learned_and_forbidden_topics(tmp_path):
    path = tmp_path / "a.toml"
    path.write_text(
        '[answers]\nenglish_level = "B2"\nsalary_expectation_es = "15,000 MXN mensuales"\n'
        '[never_answered_by_claude]\ntopics = ["reason for leaving", "notice period"]\n',
        encoding="utf-8",
    )
    text = answers.render_for_prompt(
        answers.load_applicant_answers(path),
        [{"language": "es", "question": "¿Looker?", "answer": "No."}],
    )
    assert "english_level: B2" in text and "15,000 MXN" in text
    assert "¿Looker?" in text and "No." in text
    assert "NUNCA contestes" in text and "notice period" in text


def test_render_with_nothing_approved_says_so():
    assert "no contestes" in answers.render_for_prompt({}, []).lower()


# --------------------------------------------------------------- outcomes ---

U1, U2, U3 = "https://x.com/1", "https://x.com/2", "https://x.com/3"


def test_parse_fenced_json_block_after_chatter():
    text = 'Listo.\n```json\n{"outcomes":[{"url":"%s","status":"applied","evidence":"Te postulaste correctamente"}]}\n```' % U1
    [outcome] = outcomes.parse_batch_result(text, [U1])
    assert outcome.status == "applied"


def test_parse_bare_json_and_bare_list():
    bare = '{"outcomes":[{"url":"%s","status":"skipped","reason":"captcha"}]}' % U1
    assert outcomes.parse_batch_result(bare, [U1])[0].reason == SkipReason.CAPTCHA
    as_list = '[{"url":"%s","status":"skipped","reason":"offer_gone"}]' % U1
    assert outcomes.parse_batch_result(as_list, [U1])[0].reason == SkipReason.OFFER_GONE


def test_applied_without_evidence_is_never_trusted():
    text = json.dumps({"outcomes": [{"url": U1, "status": "applied"}, {"url": U2, "status": "applied", "evidence": "ok"}]})
    first, second = outcomes.parse_batch_result(text, [U1, U2])
    assert first.status == "pending" and second.status == "pending"


def test_missing_garbage_and_unknown_urls():
    assert outcomes.parse_batch_result("no json at all", [U1, U2])[0].status == "pending"
    assert [o.status for o in outcomes.parse_batch_result("", [U1])] == ["pending"]
    text = json.dumps({"outcomes": [{"url": "https://evil.com/x", "status": "applied", "evidence": "Te postulaste"}]})
    assert outcomes.parse_batch_result(text, [U1])[0].status == "pending"


def test_unknown_reason_becomes_other_and_missing_reason_too():
    text = json.dumps({"outcomes": [{"url": U1, "status": "skipped", "reason": "weird"},
                                    {"url": U2, "status": "skipped"}]})
    first, second = outcomes.parse_batch_result(text, [U1, U2])
    assert first.reason == SkipReason.OTHER and second.reason == SkipReason.OTHER


def test_pending_question_needs_the_question_text():
    text = json.dumps({"outcomes": [{"url": U1, "status": "skipped", "reason": "pending_question"},
                                    {"url": U2, "status": "skipped", "reason": "pending_question", "question": "¿Looker?"}]})
    first, second = outcomes.parse_batch_result(text, [U1, U2])
    assert first.reason == SkipReason.OTHER
    assert second.reason == SkipReason.PENDING_QUESTION and second.question == "¿Looker?"


def test_results_keep_the_expected_order_and_count():
    text = json.dumps({"outcomes": [{"url": U2, "status": "skipped", "reason": "captcha"}]})
    results = outcomes.parse_batch_result(text, [U1, U2, U3])
    assert [o.url for o in results] == [U1, U2, U3]


# ----------------------------------------------- client + record_outcomes ---


class _FakeRove:
    def __init__(self, fail_paths=()):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.fail_paths = set(fail_paths)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        if request.url.path in self.fail_paths:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"ok": True, "items": [], "urls": []})


def _client(fake):
    return RoveClient("http://rove.test", transport=httpx.MockTransport(fake))


def _cand(sig, url, title="T", company="C", source="occ"):
    return Candidate(signature=sig, url=url, title=title, company=company, source=source, grade="B", score=70, days_old=1)


def test_record_routes_each_outcome_to_the_right_place():
    fake = _FakeRove()
    cands = {U1: _cand("s1", U1), U2: _cand("s2", U2), U3: _cand("s3", "https://x.com/3")}
    cands["https://x.com/4"] = _cand("s4", "https://x.com/4")
    cands["https://x.com/5"] = _cand("s5", "https://x.com/5")
    outs = [
        outcomes.Outcome(url=U1, status="applied", evidence="Te postulaste correctamente"),
        outcomes.Outcome(url=U2, status="skipped", reason=SkipReason.SUSPECTED_SCAM),
        outcomes.Outcome(url="https://x.com/3", status="skipped", reason=SkipReason.GOVERNMENT_ID, note="CURP"),
        outcomes.Outcome(url="https://x.com/4", status="skipped", reason=SkipReason.PENDING_QUESTION, question="¿Looker?"),
        outcomes.Outcome(url="https://x.com/5", status="pending", note="se acabó el tiempo"),
    ]
    recorded = outcomes.record_outcomes(_client(fake), cands, outs)

    paths = [(m, p) for m, p, _ in fake.calls]
    assert ("POST", "/track") in paths
    tracks = [b for _, p, b in fake.calls if p == "/track"]
    assert {"signature": "s1", "action": "applied"} in tracks
    assert {"signature": "s2", "action": "dismissed"} in tracks
    skipped_body = next(b for _, p, b in fake.calls if p == "/nightly/skipped")
    assert skipped_body["reason"] == "government_id" and skipped_body["signature"] == "s3"
    question_body = next(b for _, p, b in fake.calls if p == "/nightly/questions")
    assert question_body["question"] == "¿Looker?" and question_body["vacancy"]["url"] == "https://x.com/4"
    assert len(fake.calls) == 4  # the pending one writes nothing
    assert (len(recorded.applied), len(recorded.dismissed), len(recorded.for_kevin),
            len(recorded.questions), len(recorded.pending)) == (1, 1, 1, 1, 1)


def test_a_failed_call_is_collected_not_raised_and_the_rest_continue():
    fake = _FakeRove(fail_paths={"/track"})
    cands = {U1: _cand("s1", U1), U2: _cand("s2", U2)}
    outs = [
        outcomes.Outcome(url=U1, status="applied", evidence="Te postulaste correctamente"),
        outcomes.Outcome(url=U2, status="skipped", reason=SkipReason.CAPTCHA),
    ]
    recorded = outcomes.record_outcomes(_client(fake), cands, outs)
    assert len(recorded.errors) == 1 and recorded.applied == []
    assert len(recorded.for_kevin) == 1


def test_unknown_candidate_urls_are_ignored():
    fake = _FakeRove()
    recorded = outcomes.record_outcomes(
        _client(fake), {}, [outcomes.Outcome(url=U1, status="applied", evidence="Te postulaste correctamente")]
    )
    assert fake.calls == [] and recorded.applied == []


def test_client_reads_raise_on_http_errors():
    client = _client(_FakeRove(fail_paths={"/nightly/settings"}))
    with pytest.raises(httpx.HTTPStatusError):
        client.get_settings()


def test_a_single_unwrapped_outcome_object_is_accepted():
    text = '{"url": "%s", "status": "skipped", "reason": "captcha"}' % U1
    assert outcomes.parse_batch_result(text, [U1])[0].reason == SkipReason.CAPTCHA


def test_clean_url_strips_tracking_but_keeps_the_posting():
    occ = "https://www.occ.com.mx/empleo/oferta/21414171-analista-sr-de-bi-home-office?rank=1&sessionid=&uuid=abc&origin=unknown"
    assert selector.clean_url(occ) == "https://www.occ.com.mx/empleo/oferta/21414171-analista-sr-de-bi-home-office"
    ct = "https://mx.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123#lc=ListOffers-Score3-8"
    assert selector.clean_url(ct) == "https://mx.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123"
    assert selector.clean_url("https://x.com/job?id=7#top") == "https://x.com/job?id=7"  # query kept elsewhere


def test_candidates_use_clean_urls_and_dedupe_by_them():
    a = _item("a", url="https://www.occ.com.mx/empleo/oferta/1-x?rank=1&uuid=aaa")
    b = _item("b", url="https://www.occ.com.mx/empleo/oferta/1-x?rank=9&uuid=bbb")  # same posting, other session
    result = selector.candidates_from_inbox(_inbox(a, b))
    assert [c.url for c in result] == ["https://www.occ.com.mx/empleo/oferta/1-x"]
    skipped = selector.candidates_from_inbox(_inbox(a), exclude_urls={"https://www.occ.com.mx/empleo/oferta/1-x"})
    assert skipped == []
