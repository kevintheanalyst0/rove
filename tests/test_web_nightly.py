"""Routes for the nightly run's kill switch and review lists (EATP-037).
Never touches the pipeline, AI or the network (CLAUDE.md §7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rove import config
from rove.events import EventBus
from rove.web.server import create_app

URL = "https://www.occ.com.mx/empleo/oferta/21414171-analista-sr-de-bi-home-office/"


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(config, "NIGHTLY_SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "NIGHTLY_SKIPPED_FILE", tmp_path / "skipped.jsonl")
    monkeypatch.setattr(config, "NIGHTLY_QUESTIONS_FILE", tmp_path / "questions.jsonl")
    monkeypatch.setattr(config, "NIGHTLY_LEARNED_ANSWERS_FILE", tmp_path / "learned.jsonl")
    app = create_app(event_bus=EventBus(), pipeline_run=lambda **_: None, reset_run_data=lambda: None)
    return TestClient(app, base_url="http://127.0.0.1:8000")


# --------------------------------------------------------------- settings ---


def test_settings_default_to_off_and_report_why(client):
    data = client.get("/nightly/settings").json()
    assert data["enabled"] is False and data["allowed"] is False and data["reason"] == "apagado"
    assert data["weekly_cap_pct"] == 70


def test_turn_on_and_it_is_allowed(client):
    data = client.post("/nightly/settings", json={"enabled": True}).json()
    assert data["enabled"] is True and data["allowed"] is True


def test_partial_updates_keep_other_fields(client):
    client.post("/nightly/settings", json={"enabled": True, "weekly_cap_pct": 55})
    data = client.post("/nightly/settings", json={"skip_next_run": True}).json()
    assert data["enabled"] is True and data["weekly_cap_pct"] == 55
    assert data["skip_next_run"] is True and data["allowed"] is False


def test_pause_until_and_clear_pause(client):
    client.post("/nightly/settings", json={"enabled": True, "pause_until": "2999-01-01"})
    assert client.get("/nightly/settings").json()["allowed"] is False
    data = client.post("/nightly/settings", json={"clear_pause": True}).json()
    assert data["pause_until"] is None and data["allowed"] is True


def test_consume_skip_clears_the_skip_only(client):
    client.post("/nightly/settings", json={"enabled": True, "skip_next_run": True})
    data = client.post("/nightly/consume-skip").json()
    assert data["skip_next_run"] is False and data["enabled"] is True and data["allowed"] is True


@pytest.mark.parametrize("bad", [0, 9, 101, "abc", None])
def test_invalid_cap_is_rejected_and_nothing_changes(client, bad):
    client.post("/nightly/settings", json={"enabled": True, "weekly_cap_pct": 70})
    response = client.post("/nightly/settings", json={"weekly_cap_pct": bad})
    if bad is None:  # null == "unchanged", a valid no-op
        assert response.status_code == 200
    else:
        assert response.status_code == 422
    assert client.get("/nightly/settings").json()["weekly_cap_pct"] == 70


def test_invalid_pause_date_is_rejected(client):
    assert client.post("/nightly/settings", json={"pause_until": "mañana"}).status_code == 422


# ---------------------------------------------------------------- skipped ---


def test_skipped_round_trip_and_done(client):
    created = client.post(
        "/nightly/skipped",
        json={"url": URL, "reason": "government_id", "title": "Analista Sr. de BI", "company": "MAXIMSLLC", "source": "occ"},
    ).json()
    items = client.get("/nightly/skipped").json()["items"]
    assert [i["id"] for i in items] == [created["id"]]
    assert items[0]["reason"] == "government_id"

    assert client.post(f"/nightly/skipped/{created['id']}/done").status_code == 200
    assert client.get("/nightly/skipped").json()["items"] == []


def test_skipped_unknown_id_is_404(client):
    assert client.post("/nightly/skipped/nope/done").status_code == 404


@pytest.mark.parametrize("bad_url", ["javascript:alert(1)", "data:text/html,x", "//evil.com", "nope"])
def test_skipped_rejects_non_http_urls(client, bad_url):
    response = client.post("/nightly/skipped", json={"url": bad_url, "reason": "other"})
    assert response.status_code == 422
    assert client.get("/nightly/skipped").json()["items"] == []


def test_skipped_rejects_unknown_reason_and_overlong_fields(client):
    assert client.post("/nightly/skipped", json={"url": URL, "reason": "because"}).status_code == 422
    assert client.post("/nightly/skipped", json={"url": URL, "reason": "other", "note": "x" * 501}).status_code == 422
    assert client.post("/nightly/skipped", json={"url": URL, "reason": "other", "title": "x" * 301}).status_code == 422


# -------------------------------------------------------------- questions ---


def test_question_answer_flow_saves_learned_answer(client):
    created = client.post(
        "/nightly/questions",
        json={"question": "¿Qué plataformas de e-commerce has manejado?", "language": "es", "vacancy": {"url": URL, "title": "Analista de Ecommerce"}},
    ).json()
    assert [q["id"] for q in client.get("/nightly/questions").json()["items"]] == [created["id"]]

    answered = client.post(f"/nightly/questions/{created['id']}/answer", json={"answer": "No tengo experiencia."}).json()
    assert answered["status"] == "answered" and answered["answer"] == "No tengo experiencia."
    assert client.get("/nightly/questions").json()["items"] == []
    assert config.NIGHTLY_LEARNED_ANSWERS_FILE.exists()


def test_question_validation(client):
    ok_vacancy = {"url": URL}
    assert client.post("/nightly/questions", json={"question": "", "vacancy": ok_vacancy}).status_code == 422
    assert client.post("/nightly/questions", json={"question": "x" * 1001, "vacancy": ok_vacancy}).status_code == 422
    assert client.post("/nightly/questions", json={"question": "q", "language": "fr", "vacancy": ok_vacancy}).status_code == 422
    assert client.post("/nightly/questions", json={"question": "q", "vacancy": {"url": "javascript:1"}}).status_code == 422
    assert client.get("/nightly/questions").json()["items"] == []


def test_answer_validation_and_unknown_id(client):
    created = client.post("/nightly/questions", json={"question": "q", "vacancy": {"url": URL}}).json()
    assert client.post(f"/nightly/questions/{created['id']}/answer", json={"answer": ""}).status_code == 422
    assert client.post(f"/nightly/questions/{created['id']}/answer", json={"answer": "x" * 2001}).status_code == 422
    assert client.post("/nightly/questions/nope/answer", json={"answer": "ok"}).status_code == 404


# ------------------------------------------------------------ same-origin ---


@pytest.mark.parametrize(
    "path,body",
    [
        ("/nightly/settings", {"enabled": True}),
        ("/nightly/consume-skip", None),
        ("/nightly/skipped", {"url": URL, "reason": "other"}),
        ("/nightly/skipped/abc/done", None),
        ("/nightly/questions", {"question": "q", "vacancy": {"url": URL}}),
        ("/nightly/questions/abc/answer", {"answer": "x"}),
    ],
)
def test_every_post_blocks_a_foreign_origin(client, path, body):
    response = client.post(path, json=body, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.get("/nightly/settings").json()["enabled"] is False


def test_post_without_origin_header_is_allowed_like_the_runner_does(client):
    # The PC-side runner is not a browser: no Origin header, Tailscale Host.
    assert client.post("/nightly/settings", json={"enabled": True}).status_code == 200


# ------------------------------------------------------------- dashboard ---


def test_dashboard_wires_the_nightly_panel(client):
    html = client.get("/").text
    assert 'id="nightlyBtn"' in html and 'id="sideNightlyBtn"' in html
    js = client.get("/static/js/app.js").text
    assert "openNightlyModal" in js and "/nightly/settings" in js and "safeHttpUrl" in js
    assert "javascript:" not in js  # links are only ever rendered for http(s) URLs
