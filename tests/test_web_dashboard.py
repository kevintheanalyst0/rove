"""Results dashboard backend (EATP-016): GET /results, POST /track.

Same discipline as test_web_server.py — a private EventBus per test (unused
here, but create_app() always wants one) and config paths monkeypatched
under tmp_path, never the real data/ directory.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from career_radar import config
from career_radar.events import EventBus
from career_radar.models import Job, RunResult, RunStatus, ScoredJob
from career_radar.storage import write_json
from career_radar.tracking.store import TrackingAction
from career_radar.web.server import create_app


def _make_client() -> TestClient:
    app = create_app(event_bus=EventBus(), pipeline_run=lambda **_: None)
    return TestClient(app)


def _scored_job(signature: str = "sig-1") -> ScoredJob:
    job = Job(
        source="occ",
        source_job_id="1",
        signature=signature,
        title="Analista de Datos",
        company="Acme",
        description="x" * 250,
        url="https://example.com/1",
        remote_status="remote",
        days_old=1,
    )
    return ScoredJob(
        job=job, prefilter_score=90, prefilter_passed=True, ai_evaluated=True, ai_score=90,
        pros=["Buen stack"], contras=[], summary="Buen puesto.",
    )


def test_results_empty_when_no_run_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_FILE", tmp_path / "results.json")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    response = _make_client().get("/results")

    assert response.status_code == 200
    assert response.json() == {"result": None, "tracking": {}}


def test_results_returns_persisted_run_with_tracking_merged(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_FILE", tmp_path / "results.json")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    scored = _scored_job()
    result = RunResult(
        started_at=datetime.now(UTC), finished_at=datetime.now(UTC), status=RunStatus.SUCCESS,
        message="1 vacante encontrada", jobs=[scored], new_signatures=[scored.job.signature],
    )
    write_json(config.RESULTS_FILE, result.model_dump(mode="json"))

    client = _make_client()
    client.post("/track", json={"signature": scored.job.signature, "action": "applied"})

    response = client.get("/results")
    data = response.json()

    assert data["result"]["jobs"][0]["job"]["title"] == "Analista de Datos"
    assert data["result"]["new_signatures"] == [scored.job.signature]
    assert data["tracking"] == {scored.job.signature: "applied"}


def test_track_dismissed_then_results_reflects_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_FILE", tmp_path / "results.json")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    client = _make_client()
    response = client.post("/track", json={"signature": "sig-1", "action": "dismissed"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "signature": "sig-1", "action": "dismissed"}
    assert client.get("/results").json()["tracking"] == {"sig-1": "dismissed"}


def test_track_a_later_action_overrides_an_earlier_one(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    client = _make_client()
    client.post("/track", json={"signature": "sig-1", "action": "dismissed"})
    client.post("/track", json={"signature": "sig-1", "action": "applied"})

    assert client.get("/results").json()["tracking"] == {"sig-1": "applied"}


def test_track_rejects_an_invalid_action(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    response = _make_client().post("/track", json={"signature": "sig-1", "action": "maybe"})

    assert response.status_code == 422


def test_track_action_enum_values_match_the_wire_strings():
    assert TrackingAction.APPLIED.value == "applied"
    assert TrackingAction.DISMISSED.value == "dismissed"
