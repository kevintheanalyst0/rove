"""Results dashboard backend (EATP-016): GET /results, POST /track.

Same discipline as test_web_server.py — a private EventBus per test (unused
here, but create_app() always wants one) and config paths monkeypatched
under tmp_path, never the real data/ directory.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from rove import config
from rove.apply import store as apply_store
from rove.apply.store import ApplicationEntry, ApplicationStatus
from rove.events import EventBus
from rove.inbox import store as inbox_store
from rove.models import Job, RunResult, RunStatus, ScoredJob
from rove.storage import write_json
from rove.tracking.store import TrackingAction
from rove.web.server import create_app


def _make_client(submit_application=None) -> TestClient:
    kwargs = {"event_bus": EventBus(), "pipeline_run": lambda **_: None}
    if submit_application is not None:
        kwargs["submit_application"] = submit_application
    app = create_app(**kwargs)
    # EATP-026: see test_web_server.py's _make_client for why base_url is set.
    return TestClient(app, base_url="http://127.0.0.1:8000")


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


# ---------------------------------------------------------------------------
# Accumulated inbox (EATP-031): GET /inbox
# ---------------------------------------------------------------------------


def test_inbox_empty_when_nothing_accumulated_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    response = _make_client().get("/inbox")

    assert response.status_code == 200
    assert response.json() == {
        "buckets": {"hoy": [], "ayer": [], "esta_semana": [], "mas_viejo": []},
        "total": 0,
    }


def test_inbox_returns_an_accumulated_job_bucketed_as_today(tmp_path, monkeypatch):
    from rove.inbox import store as inbox_store

    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    scored = _scored_job("sig-1")
    inbox_store.append_run([scored], datetime.now(UTC))

    response = _make_client().get("/inbox")
    data = response.json()

    assert data["total"] == 1
    assert len(data["buckets"]["hoy"]) == 1
    assert data["buckets"]["hoy"][0]["signature"] == "sig-1"
    assert data["buckets"]["hoy"][0]["scored"]["job"]["title"] == "Analista de Datos"


def test_inbox_excludes_a_job_kevin_already_tracked(tmp_path, monkeypatch):
    from rove.inbox import store as inbox_store

    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    inbox_store.append_run(
        [_scored_job("sig-1"), _scored_job("sig-2")], datetime.now(UTC)
    )

    client = _make_client()
    client.post("/track", json={"signature": "sig-1", "action": "dismissed"})

    data = client.get("/inbox").json()

    signatures = {job["signature"] for bucket in data["buckets"].values() for job in bucket}
    assert signatures == {"sig-2"}
    assert data["total"] == 1


def test_inbox_orders_each_bucket_best_score_first(tmp_path, monkeypatch):
    from rove.inbox import store as inbox_store
    from rove.models import Job, ScoredJob

    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    def _scored(signature: str, score: int) -> ScoredJob:
        job = Job(
            source="occ", source_job_id=signature, signature=signature,
            title="Data Analyst", company="Acme", description="x" * 250,
            url=f"https://example.com/{signature}",
        )
        return ScoredJob(
            job=job, prefilter_score=score, prefilter_passed=True,
            ai_evaluated=True, ai_score=score,
        )

    inbox_store.append_run(
        [_scored("low", 60), _scored("high", 95)], datetime.now(UTC)
    )

    data = _make_client().get("/inbox").json()

    assert [job["signature"] for job in data["buckets"]["hoy"]] == ["high", "low"]


# ---------------------------------------------------------------------------
# Match-quality labeling (EATP-017): GET /eval/labels, POST /eval/label
# ---------------------------------------------------------------------------


def test_eval_labels_empty_when_nothing_labeled_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVAL_LABELS_FILE", tmp_path / "labels.jsonl")

    assert _make_client().get("/eval/labels").json() == {}


def test_label_good_then_labels_reflects_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVAL_LABELS_FILE", tmp_path / "labels.jsonl")

    client = _make_client()
    response = client.post("/eval/label", json={"signature": "sig-1", "label": "good"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "signature": "sig-1", "label": "good", "reason": None}

    labels = client.get("/eval/labels").json()
    assert labels["sig-1"]["label"] == "good"
    assert labels["sig-1"]["reason"] is None


def test_label_bad_with_reason_is_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVAL_LABELS_FILE", tmp_path / "labels.jsonl")

    client = _make_client()
    client.post("/eval/label", json={"signature": "sig-1", "label": "bad", "reason": "not_remote"})

    labels = client.get("/eval/labels").json()
    assert labels["sig-1"]["label"] == "bad"
    assert labels["sig-1"]["reason"] == "not_remote"


def test_a_later_label_overrides_an_earlier_one_for_the_same_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVAL_LABELS_FILE", tmp_path / "labels.jsonl")

    client = _make_client()
    client.post("/eval/label", json={"signature": "sig-1", "label": "bad", "reason": "off_role"})
    client.post("/eval/label", json={"signature": "sig-1", "label": "good"})

    labels = client.get("/eval/labels").json()
    assert labels["sig-1"]["label"] == "good"
    assert labels["sig-1"]["reason"] is None


def test_label_rejects_an_invalid_label(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVAL_LABELS_FILE", tmp_path / "labels.jsonl")

    response = _make_client().post("/eval/label", json={"signature": "sig-1", "label": "maybe"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Auto-apply (EATP-034): GET /applications, POST /applications/<sig>/send
# ---------------------------------------------------------------------------


def test_applications_empty_when_nothing_prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")

    response = _make_client().get("/applications")

    assert response.status_code == 200
    assert response.json() == {}


def test_applications_returns_prepared_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")
    apply_store.record_entry(
        ApplicationEntry(
            signature="sig-1",
            status=ApplicationStatus.DRAFT_READY,
            answers={"Why this role?": "Porque encaja con mi experiencia."},
        )
    )

    data = _make_client().get("/applications").json()

    assert data["sig-1"]["status"] == "draft_ready"
    assert data["sig-1"]["answers"] == {"Why this role?": "Porque encaja con mi experiencia."}


def test_send_application_calls_submit_and_returns_its_result(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")
    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")

    scored = _scored_job("sig-1")
    inbox_store.append_run([scored], datetime.now(UTC))
    entry = ApplicationEntry(signature="sig-1", status=ApplicationStatus.DRAFT_READY, answers={})
    apply_store.record_entry(entry)

    calls: list[tuple] = []

    def fake_submit(job, profile, entry_arg, **kwargs):
        calls.append((job, profile, entry_arg))
        return entry_arg.model_copy(update={"status": ApplicationStatus.SUBMITTED})

    client = _make_client(submit_application=fake_submit)
    response = client.post("/applications/sig-1/send")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "signature": "sig-1", "result": "submitted", "note": None}
    assert len(calls) == 1
    assert calls[0][0].signature == "sig-1"


def test_send_application_404_when_no_draft_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")

    response = _make_client().post("/applications/does-not-exist/send")

    assert response.status_code == 404


def test_send_application_409_when_not_draft_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")
    apply_store.record_entry(
        ApplicationEntry(signature="sig-1", status=ApplicationStatus.MANUAL_REQUIRED, note="captcha")
    )

    response = _make_client().post("/applications/sig-1/send")

    assert response.status_code == 409
    assert response.json()["current_status"] == "manual_required"


def test_send_application_404_when_job_missing_from_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")
    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")
    apply_store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.DRAFT_READY))

    response = _make_client().post("/applications/sig-1/send")

    assert response.status_code == 404
