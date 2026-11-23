"""The nightly run end to end with fakes (EATP-037 phase 2): a stateful fake Rove,
a fake `claude`, fake phone/keep-awake/hibernate. Never touches Claude, Chrome,
Windows or the network (CLAUDE.md §7)."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from rove.nightly import pc, prompt
from rove.nightly.client import RoveClient
from rove.nightly.quota import Quota, parse_quota
from rove.nightly.runner import ClaudeResult, Ports, RunConfig, build_summary, may_start_batch, run_night


def _job(sig, **kw):
    return {
        "signature": sig,
        "scored": {
            "grade": kw.get("grade", "B"),
            "final_score": kw.get("score", 70),
            "job": {"title": kw.get("title", "Analista de datos"), "company": f"Co {sig}", "source": kw.get("source", "occ"),
                    "days_old": 1, "url": f"https://jobs.test/{sig}"},
        },
    }


class FakeRove:
    def __init__(self, *, jobs, settings=None, fail=()):
        self.inbox = {"buckets": {"hoy": [_job(s) if isinstance(s, str) else s for s in jobs]}, "total": len(jobs)}
        self.settings = {"enabled": True, "allowed": True, "reason": "encendido", "skip_next_run": False,
                         "weekly_cap_pct": 70, **(settings or {})}
        self.fail = set(fail)
        self.posts: list[tuple[str, dict | None]] = []
        self.retry: list[str] = []
        self.learned: list[dict] = []
        self.skipped_urls: list[str] = []
        self.open_questions: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in self.fail:
            return httpx.Response(500)
        if request.method == "GET":
            data = {
                "/nightly/settings": self.settings,
                "/inbox": self.inbox,
                "/nightly/retry": {"urls": self.retry},
                "/nightly/learned-answers": {"items": self.learned},
                "/nightly/skipped": {"items": [{"url": u} for u in self.skipped_urls]},
                "/nightly/questions": {"items": self.open_questions},
            }[path]
            return httpx.Response(200, json=data)
        self.posts.append((path, json.loads(request.content) if request.content else None))
        return httpx.Response(200, json={"ok": True})


class Harness:
    def __init__(self, tmp_path: Path, rove: FakeRove, *, quotas, claude):
        self.rove = rove
        self.notices: list[tuple[str, str]] = []
        self.prompts: list[str] = []
        self.hibernated = 0
        self.awake = {"in": 0, "out": 0}
        self._quotas = list(quotas)
        self._claude = claude

        def read_quota():
            return self._quotas.pop(0) if len(self._quotas) > 1 else self._quotas[0]

        def run_claude(text):
            self.prompts.append(text)
            return self._claude(text, len(self.prompts))

        @contextlib.contextmanager
        def keep_awake():
            self.awake["in"] += 1
            try:
                yield
            finally:
                self.awake["out"] += 1

        def hibernate():
            self.hibernated += 1
            return True

        self.ports = Ports(
            client=RoveClient("http://rove.test", transport=httpx.MockTransport(rove)),
            read_quota=read_quota,
            run_claude=run_claude,
            notify=lambda t, m: self.notices.append((t, m)),
            keep_awake=keep_awake,
            hibernate_if_idle=hibernate,
            applicant_answers=lambda: {"answers": {"english_level": "B2"}},
            now=lambda: datetime(2026, 11, 23, 9, 0, tzinfo=UTC),  # 3:00 a. m. in Mexico City
            progress_dir=tmp_path / "progress",
        )

    def tracked(self, action):
        return [b["signature"] for p, b in self.rove.posts if p == "/track" and b["action"] == action]


OK_QUOTA = Quota(session_pct=40, weekly_pct=45)


def _all_applied(text, _n):
    urls = [line.strip() for line in text.splitlines() if line.strip().startswith("https://jobs.test/")]
    outcomes = [{"url": u, "status": "applied", "evidence": "Te postulaste correctamente"} for u in urls]
    return ClaudeResult(ok=True, text="```json\n" + json.dumps({"outcomes": outcomes}) + "\n```")


# --------------------------------------------------------- fail-closed gates ---


def test_switch_off_does_nothing_and_is_silent(tmp_path):
    rove = FakeRove(jobs=["a"], settings={"enabled": False, "allowed": False, "reason": "apagado"})
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "off" and h.prompts == [] and h.notices == [] and h.hibernated == 0


def test_skip_next_run_is_honoured_once_and_consumed(tmp_path):
    rove = FakeRove(jobs=["a"], settings={"allowed": False, "skip_next_run": True, "reason": "saltar la próxima corrida"})
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "skipped" and h.prompts == []
    assert ("/nightly/consume-skip", None) in rove.posts


def test_unreadable_switch_fails_closed_and_tells_kevin(tmp_path):
    rove = FakeRove(jobs=["a"], fail={"/nightly/settings"})
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "no_switch" and h.prompts == []
    assert "interruptor" in h.notices[0][1]


def test_unreadable_quota_fails_closed(tmp_path):
    h = Harness(tmp_path, FakeRove(jobs=["a"]), quotas=[None], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "no_quota" and h.prompts == [] and "cuota" in h.notices[0][1]


def test_weekly_cap_blocks_the_whole_run(tmp_path):
    h = Harness(tmp_path, FakeRove(jobs=["a"]), quotas=[Quota(session_pct=10, weekly_pct=72)], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "weekly_cap" and h.prompts == [] and "72" in h.notices[0][1]


def test_unreadable_inbox_is_reported_and_releases_the_pc(tmp_path):
    h = Harness(tmp_path, FakeRove(jobs=["a"], fail={"/inbox"}), quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "no_inbox" and h.prompts == []
    assert h.awake == {"in": 1, "out": 1} and "bandeja" in h.notices[0][1]


# ------------------------------------------------------------------ happy path ---


def test_happy_path_batches_marks_summarises_and_sleeps(tmp_path):
    rove = FakeRove(jobs=["a", "b", "c", "d", "e"])
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports, RunConfig(batch_size=2))
    assert report.status == "ran" and report.batches == 3 and report.attempted == 5 and report.applied == 5
    assert sorted(h.tracked("applied")) == ["a", "b", "c", "d", "e"]
    assert h.awake == {"in": 1, "out": 1} and h.hibernated == 1
    assert h.notices[-1][0] == "Corrida nocturna terminada" and "5 enviadas" in h.notices[-1][1]
    assert report.stop_reason == "se acabaron las vacantes elegibles"


def test_stops_at_the_nightly_cap(tmp_path):
    rove = FakeRove(jobs=list("abcdefgh"))
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports, RunConfig(max_per_night=5, batch_size=2))
    assert report.attempted == 5 and [p.count("https://jobs.test/") for p in h.prompts] == [2, 2, 1]
    assert "tope de 5" in report.stop_reason


def test_stops_starting_batches_when_the_window_reaches_90(tmp_path):
    rove = FakeRove(jobs=list("abcdef"))
    # preflight 40 (reused for batch 1), before batch 2 -> 91, final read -> 91
    h = Harness(tmp_path, rove, quotas=[Quota(40, 45), Quota(91, 50)], claude=_all_applied)
    report = run_night(h.ports, RunConfig(batch_size=2))
    assert report.batches == 1 and report.applied == 2 and "ventana" in report.stop_reason
    assert report.quota_end.session_pct == 91


def test_quota_becoming_unreadable_mid_run_stops_it(tmp_path):
    h = Harness(tmp_path, FakeRove(jobs=list("abcd")), quotas=[OK_QUOTA, None], claude=_all_applied)
    report = run_night(h.ports, RunConfig(batch_size=2))
    assert report.batches == 1 and "cuota" in report.stop_reason


def test_nothing_eligible_says_so(tmp_path):
    rove = FakeRove(jobs=[_job("a", source="greenhouse"), _job("b", title="Ejecutivo de ventas")])
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "nothing_to_do" and h.prompts == [] and h.hibernated == 1
    assert "No había vacantes" in h.notices[0][1]


# ---------------------------------------------------------------- outcomes -> Rove ---


def test_mixed_outcomes_land_in_the_right_lists(tmp_path):
    def claude(text, _n):
        outcomes = [
            {"url": "https://jobs.test/a", "status": "applied", "evidence": "Te postulaste correctamente"},
            {"url": "https://jobs.test/b", "status": "skipped", "reason": "government_id", "note": "CURP"},
            {"url": "https://jobs.test/c", "status": "skipped", "reason": "suspected_scam"},
            {"url": "https://jobs.test/d", "status": "skipped", "reason": "pending_question", "question": "¿Looker?", "language": "es"},
        ]
        return ClaudeResult(ok=True, text=json.dumps({"outcomes": outcomes}))

    rove = FakeRove(jobs=list("abcde"))
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=claude)
    report = run_night(h.ports, RunConfig(batch_size=5))
    assert (report.applied, report.for_kevin, report.dismissed, report.questions, report.pending) == (1, 1, 1, 1, 1)
    assert h.tracked("applied") == ["a"] and h.tracked("dismissed") == ["c"]
    assert any(p == "/nightly/skipped" and b["reason"] == "government_id" for p, b in rove.posts)
    assert any(p == "/nightly/questions" and b["question"] == "¿Looker?" for p, b in rove.posts)


def test_an_unconfirmed_application_is_never_marked_applied(tmp_path):
    def claude(text, _n):
        return ClaudeResult(ok=True, text='{"outcomes":[{"url":"https://jobs.test/a","status":"applied"}]}')

    h = Harness(tmp_path, FakeRove(jobs=["a"]), quotas=[OK_QUOTA], claude=claude)
    report = run_night(h.ports)
    assert report.applied == 0 and report.pending == 1 and h.tracked("applied") == []


def test_progress_file_is_written_and_a_second_run_does_not_repeat_vacancies(tmp_path):
    rove = FakeRove(jobs=["a", "b"])
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    run_night(h.ports)
    progress = tmp_path / "progress" / "2026-11-23.jsonl"
    lines = [json.loads(line) for line in progress.read_text(encoding="utf-8").splitlines()]
    assert {entry["url"] for entry in lines} == {"https://jobs.test/a", "https://jobs.test/b"}
    assert all(entry["status"] == "applied" for entry in lines)

    h.prompts.clear()
    second = run_night(h.ports)  # same fake inbox, same night
    assert second.status == "nothing_to_do" and h.prompts == []


def test_skipped_urls_and_retries_are_respected(tmp_path):
    rove = FakeRove(jobs=["a", "b", "c"])
    rove.skipped_urls = ["https://jobs.test/a"]
    rove.retry = ["https://jobs.test/c"]
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    run_night(h.ports, RunConfig(batch_size=5))
    urls = [line.strip() for line in h.prompts[0].splitlines() if line.strip().startswith("https://jobs.test/")]
    assert urls == ["https://jobs.test/c", "https://jobs.test/b"]  # retry first, skipped one absent


# --------------------------------------------------------------- failures ---


def test_a_failing_batch_marks_nothing_and_two_in_a_row_stop_the_night(tmp_path):
    def claude(text, _n):
        return ClaudeResult(ok=False, error="error_max_turns")

    rove = FakeRove(jobs=list("abcdef"))
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=claude)
    report = run_night(h.ports, RunConfig(batch_size=2))
    assert report.batches == 2 and report.failures == 2 and "fallaron" in report.stop_reason
    assert rove.posts == [] and report.pending == 4
    assert h.awake == {"in": 1, "out": 1} and h.hibernated == 1


def test_a_failed_batch_that_reported_confirmed_applications_still_records_them(tmp_path):
    def claude(text, _n):
        body = {"outcomes": [{"url": "https://jobs.test/a", "status": "applied", "evidence": "Te postulaste correctamente"}]}
        return ClaudeResult(ok=False, text=json.dumps(body), error="error_max_turns")

    rove = FakeRove(jobs=["a", "b"])
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=claude)
    report = run_night(h.ports, RunConfig(batch_size=2))
    assert h.tracked("applied") == ["a"] and report.applied == 1 and report.failures == 1 and report.pending == 1


def test_a_crashing_claude_port_does_not_lose_the_night(tmp_path):
    calls = {"n": 0}

    def claude(text, n):
        calls["n"] += 1
        if n == 1:
            raise RuntimeError("boom")
        return _all_applied(text, n)

    h = Harness(tmp_path, FakeRove(jobs=list("abcd")), quotas=[OK_QUOTA], claude=claude)
    report = run_night(h.ports, RunConfig(batch_size=2))
    assert report.failures == 1 and report.applied == 2 and h.awake == {"in": 1, "out": 1}


def test_rove_write_errors_are_reported_not_raised(tmp_path):
    rove = FakeRove(jobs=["a"], fail={"/track"})
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    report = run_night(h.ports)
    assert report.status == "ran" and report.errors and "error(es) al anotar" in report.summary


# ---------------------------------------------------------- pieces and prompt ---


def test_may_start_batch_rules():
    cfg = RunConfig()
    assert may_start_batch(Quota(10, 10), 70, cfg) == (True, "")
    assert may_start_batch(Quota(10, 70), 70, cfg)[0] is False
    assert may_start_batch(Quota(90, 10), 70, cfg)[0] is False
    assert may_start_batch(Quota(89.9, 69.9), 70, cfg)[0] is True


def test_prompt_carries_the_rules_the_vacancies_and_the_approved_answers():
    from rove.nightly.selector import Candidate

    text = prompt.build_batch_prompt(
        [Candidate("s", "https://jobs.test/a", "Analista", "Acme", "occ", "B", 70, 1)], "english_level: B2"
    )
    for needle in ("captcha", "CURP", "Telegram", "contraseñas", "pending_question", "https://jobs.test/a",
                   "english_level: B2", "```json", "ya te postulaste"):
        assert needle in text


def test_parse_quota():
    good = parse_quota('{"ok":true,"session":36,"weekly":52.5,"session_resets_at":"x","weekly_resets_at":"y"}')
    assert good == Quota(36.0, 52.5, "x", "y")
    for bad in ["", "garbage", '{"ok":false,"error":"HttpRequestException"}', '{"ok":true,"session":"a","weekly":1}', '{"ok":true}']:
        assert parse_quota(bad) is None
    assert parse_quota("warning line\n" + '{"ok":true,"session":1,"weekly":2}') == Quota(1.0, 2.0, None, None)


def test_summary_text_is_compact_and_informative():
    from rove.nightly.runner import RunReport

    report = RunReport(status="ran", applied=7, for_kevin=2, questions=1, dismissed=3, pending=1,
                       quota_start=Quota(10, 50), quota_end=Quota(40, 55), stop_reason="llegué al tope de 20 vacantes")
    text = build_summary(report)
    assert "7 enviadas" in text and "2 para ti" in text and "ventana 10→40 %" in text and "semanal 50→55 %" in text
    assert len(text) < 300


def test_vigilante_config_parser_handles_comments_quotes_and_missing_file(tmp_path, monkeypatch):
    path = tmp_path / "config"
    path.write_text('# comment\nHA="http://ha.test:8123"\nNOTIFY_DEVICES="dev_a dev_b"\nexport TOKEN_FILE=/x/tok\nbroken line\n', encoding="utf-8")
    monkeypatch.setattr(pc, "VIGILANTE_CONFIG", path)
    cfg = pc._vigilante_config()
    assert cfg["HA"] == "http://ha.test:8123" and cfg["NOTIFY_DEVICES"] == "dev_a dev_b" and cfg["TOKEN_FILE"] == "/x/tok"
    monkeypatch.setattr(pc, "VIGILANTE_CONFIG", tmp_path / "missing")
    assert pc._vigilante_config() == {}


def test_notify_without_config_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "VIGILANTE_CONFIG", tmp_path / "missing")
    pc.notify("t", "m")  # logs a warning, returns


def test_dry_run_ports_never_write_to_rove(monkeypatch):
    ports = pc.real_ports(dry_run=True, cfg=RunConfig())
    assert ports.client.track("sig", "applied") == {} and ports.client.consume_skip() == {}
    assert ports.client.add_skipped("https://x.com", "captcha") == {}
    assert ports.hibernate_if_idle() is False
    assert ports.run_claude("VACANTES:\n1. x\nFORMATO DE RESPUESTA").ok is True


def test_dry_run_client_ignores_the_switch_but_keeps_the_cap():
    rove = FakeRove(jobs=["a"], settings={"enabled": False, "allowed": False, "reason": "apagado", "weekly_cap_pct": 60})
    client = pc._ReadOnlyClient("http://rove.test", transport=httpx.MockTransport(rove))
    settings = client.get_settings()
    assert settings["allowed"] is True and settings["weekly_cap_pct"] == 60 and "dry-run" in settings["reason"]


# ------------------------------------------- rate limit and notice config ---


def test_first_batch_reuses_the_preflight_reading_so_the_endpoint_is_read_once_per_gap(tmp_path):
    reads = {"n": 0}
    h = Harness(tmp_path, FakeRove(jobs=list("abcd")), quotas=[OK_QUOTA], claude=_all_applied)
    original = h.ports.read_quota

    def counting():
        reads["n"] += 1
        return original()

    h.ports.read_quota = counting
    run_night(h.ports, RunConfig(batch_size=2))
    # preflight + one read before batch 2 + the final read; none before batch 1
    assert reads["n"] == 3


def _ps_result(stdout):
    return type("R", (), {"stdout": stdout})()


def test_read_quota_waits_out_a_429_then_succeeds(monkeypatch):
    answers = ['{"ok":false,"error":"WebException","status":429,"retry_after":264}',
               '{"ok":true,"session":41,"weekly":53}']
    monkeypatch.setattr(pc, "_run_ps", lambda *a, **k: _ps_result(answers.pop(0)))
    slept = []
    assert pc.read_quota(sleep=slept.append) == Quota(41.0, 53.0, None, None)
    assert slept == [267]


def test_read_quota_gives_up_on_a_very_long_rate_limit_and_after_the_last_try(monkeypatch):
    monkeypatch.setattr(pc, "_run_ps", lambda *a, **k: _ps_result('{"ok":false,"status":429,"retry_after":3000}'))
    slept = []
    assert pc.read_quota(sleep=slept.append) is None and slept == []
    monkeypatch.setattr(pc, "_run_ps", lambda *a, **k: _ps_result("garbage"))
    assert pc.read_quota(sleep=slept.append) is None and slept == [15, 15]


def test_notify_expands_variables_and_tilde_in_the_token_path(tmp_path, monkeypatch):
    token = tmp_path / "secret-token"
    token.write_text("abc123\n", encoding="utf-8")
    config_file = tmp_path / "config"
    config_file.write_text('HA="http://ha.test:8123"\nNOTIFY_DEVICES="dev_a"\nTOKEN_FILE="$TOKEN_DIR/secret-token"\n', encoding="utf-8")
    monkeypatch.setattr(pc, "VIGILANTE_CONFIG", config_file)
    monkeypatch.setenv("TOKEN_DIR", str(tmp_path))
    sent = []
    monkeypatch.setattr(pc.httpx, "post", lambda url, **kw: sent.append((url, kw["headers"]["Authorization"], kw["json"])))
    pc.notify("Título", "Mensaje")
    assert sent == [("http://ha.test:8123/api/services/notify/dev_a", "Bearer abc123", {"title": "Título", "message": "Mensaje"})]


def test_vacancies_waiting_on_an_unanswered_question_are_not_retried_every_night(tmp_path):
    rove = FakeRove(jobs=["a", "b"])
    rove.open_questions = [{"question": "¿Databricks?", "vacancies": [{"url": "https://jobs.test/a"}]}]
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    run_night(h.ports, RunConfig(batch_size=5))
    urls = [line.strip() for line in h.prompts[0].splitlines() if line.strip().startswith("https://jobs.test/")]
    assert urls == ["https://jobs.test/b"]


def test_an_unreadable_questions_list_does_not_stop_the_night(tmp_path):
    rove = FakeRove(jobs=["a"], fail={"/nightly/questions"})
    h = Harness(tmp_path, rove, quotas=[OK_QUOTA], claude=_all_applied)
    assert run_night(h.ports).applied == 1


# ------------------------------------------ charger off before hibernating ---


def _ha_config(tmp_path, monkeypatch):
    token = tmp_path / "tok"
    token.write_text("abc\n", encoding="utf-8")
    config_file = tmp_path / "config"
    config_file.write_text(f'HA="http://ha.test:8123"\nNOTIFY_DEVICES="d"\nTOKEN_FILE="{token}"\nSWITCH=switch.laptop\n', encoding="utf-8")
    monkeypatch.setattr(pc, "VIGILANTE_CONFIG", config_file)
    monkeypatch.setattr(pc, "VIGILANTE_STATE_DIR", tmp_path / "state")


def test_hibernate_turns_the_charger_off_first_and_leaves_the_vigilante_marker(tmp_path, monkeypatch):
    _ha_config(tmp_path, monkeypatch)
    order = []
    monkeypatch.setattr(pc, "_run_ps", lambda *a, **k: _ps_result("42.0\n"))
    monkeypatch.setattr(pc.httpx, "post", lambda url, **kw: order.append(("post", url, kw["json"])) or type("R", (), {"status_code": 200})())
    monkeypatch.setattr(pc.subprocess, "run", lambda cmd, **kw: order.append(("shutdown", cmd)))
    assert pc.hibernate_if_idle(10.0) is True
    assert order[0] == ("post", "http://ha.test:8123/api/services/switch/turn_off", {"entity_id": "switch.laptop"})
    assert order[1] == ("shutdown", [pc.SHUTDOWN, "/h"])
    assert (tmp_path / "state" / "apagando").read_text(encoding="utf-8").isdigit()


def test_hibernate_does_nothing_when_kevin_is_present_or_the_idle_time_is_unreadable(tmp_path, monkeypatch):
    _ha_config(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(pc.httpx, "post", lambda *a, **k: calls.append("post"))
    monkeypatch.setattr(pc.subprocess, "run", lambda *a, **k: calls.append("shutdown"))
    for stdout in ("3.0\n", "-1\n", "garbage"):
        monkeypatch.setattr(pc, "_run_ps", lambda *a, **k: _ps_result(stdout))
        assert pc.hibernate_if_idle(10.0) is False
    assert calls == []


def test_hibernate_still_hibernates_if_the_charger_call_fails(tmp_path, monkeypatch):
    _ha_config(tmp_path, monkeypatch)
    monkeypatch.setattr(pc, "_run_ps", lambda *a, **k: _ps_result("42.0\n"))

    def boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(pc.httpx, "post", boom)
    ran = []
    monkeypatch.setattr(pc.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    assert pc.hibernate_if_idle(10.0) is True and ran == [[pc.SHUTDOWN, "/h"]]
