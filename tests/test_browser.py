"""collectors/browser.py — filesystem/process-management logic only (no real
Chromium here; that's exercised live, never in CI/tests, per CLAUDE.md golden
rule 3/8)."""

from __future__ import annotations

import subprocess
import threading
import time

from career_radar import cancellation, events
from career_radar.collectors import browser


def test_clear_manual_intervention_publishes_resolved_for_the_same_phase():
    # EATP-020: pairs with request_manual_intervention — the frontend needs
    # a matching event on the same phase to clear a stuck "resuélvela" banner.
    subscriber = events.bus.subscribe()
    try:
        browser.clear_manual_intervention("indeed")
        event = subscriber.get(timeout=1)
        assert event.phase == "collect:indeed"
        assert event.status == "intervention_resolved"
    finally:
        events.bus.unsubscribe(subscriber)


def test_bring_to_front_activates_then_nudges_the_window_to_repaint(monkeypatch):
    # Round 1 (Kevin, live): calling only .set.window.max() resized the
    # shared window but left whichever tab was already selected on screen —
    # the captcha tab itself never became visible, reading as a blank page.
    # .set.activate() (CDP Target.activateTarget) is what actually selects
    # this specific tab.
    #
    # Round 2 (Kevin, live): even with activate() added, the window's frame
    # appeared but its content never painted until he clicked it manually —
    # a WSLg compositor stale-render issue, not a wrong-tab one. A genuine
    # bounds change (maximized -> normal -> maximized) is the nudge.
    monkeypatch.setattr(browser.time, "sleep", lambda *_: None)
    # Round 3 (Kevin, live): even the repaint nudge didn't raise the window —
    # replaced with a real subprocess call in `_force_windows_foreground`,
    # which must never actually run in a unit test (spawns a real
    # powershell.exe on Kevin's own WSL box). Spy instead of letting it run.
    foreground_calls = []
    monkeypatch.setattr(browser, "_force_windows_foreground", lambda: foreground_calls.append(True))
    calls = []

    class _FakeWindow:
        def max(self) -> None:
            calls.append("max")

        def normal(self) -> None:
            calls.append("normal")

    class _FakeSet:
        def __init__(self) -> None:
            self.window = _FakeWindow()

        def activate(self) -> None:
            calls.append("activate")

    class _FakePage:
        def __init__(self) -> None:
            self.set = _FakeSet()
            self.run_js_calls = []

        def run_js(self, script: str) -> None:
            self.run_js_calls.append(script)

    page = _FakePage()
    browser.bring_to_front(page)

    assert calls == ["activate", "max", "normal", "max"]
    assert page.run_js_calls == [f"document.title = {browser._FOCUS_TITLE_MARKER!r};"]
    assert foreground_calls == [True]


def test_is_wsl_true_when_proc_version_mentions_microsoft(tmp_path):
    proc_version = tmp_path / "version"
    proc_version.write_text("Linux version 5.15.90.1-microsoft-standard-WSL2\n")

    assert browser._is_wsl(proc_version) is True


def test_is_wsl_false_on_a_real_linux_kernel(tmp_path):
    proc_version = tmp_path / "version"
    proc_version.write_text("Linux version 6.8.0-generic\n")

    assert browser._is_wsl(proc_version) is False


def test_is_wsl_false_when_proc_version_is_missing(tmp_path):
    assert browser._is_wsl(tmp_path / "does-not-exist") is False


def test_force_windows_foreground_does_nothing_off_wsl(monkeypatch):
    # Undo conftest's autouse no-op stub first — these tests exercise the
    # real `_force_windows_foreground`, with only `subprocess.run` faked.
    monkeypatch.undo()
    monkeypatch.setattr(browser, "_is_wsl", lambda: False)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("subprocess.run must not be called off WSL")

    monkeypatch.setattr(browser.subprocess, "run", _fail_if_called)

    browser._force_windows_foreground()


def test_force_windows_foreground_shells_out_to_powershell_on_wsl(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(browser, "_is_wsl", lambda: True)
    calls = []

    def _fake_run(argv, **kwargs):
        calls.append((argv, kwargs))

    monkeypatch.setattr(browser.subprocess, "run", _fake_run)

    browser._force_windows_foreground()

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[0] == "powershell.exe"
    assert browser._FOCUS_TITLE_MARKER in argv[-1]
    assert kwargs["timeout"] == 10


def test_force_windows_foreground_swallows_a_missing_powershell(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(browser, "_is_wsl", lambda: True)

    def _raise_missing(*_args, **_kwargs):
        raise FileNotFoundError("powershell.exe not found")

    monkeypatch.setattr(browser.subprocess, "run", _raise_missing)

    browser._force_windows_foreground()  # must not raise


def test_force_windows_foreground_swallows_a_timeout(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(browser, "_is_wsl", lambda: True)

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell.exe", timeout=10)

    monkeypatch.setattr(browser.subprocess, "run", _raise_timeout)

    browser._force_windows_foreground()  # must not raise


def test_clear_session_restore_state_deletes_session_files(tmp_path):
    sessions_dir = tmp_path / "Default" / "Sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "Session_123").write_bytes(b"stale")
    (sessions_dir / "Tabs_456").write_bytes(b"stale")

    browser._clear_session_restore_state(str(tmp_path))

    assert list(sessions_dir.iterdir()) == []


def test_clear_session_restore_state_leaves_cookies_and_login_data_alone(tmp_path):
    default_dir = tmp_path / "Default"
    (default_dir / "Sessions").mkdir(parents=True)
    (default_dir / "Sessions" / "Session_123").write_bytes(b"stale")
    (default_dir / "Cookies").write_bytes(b"real cookies db")
    (default_dir / "Login Data").write_bytes(b"real login data")

    browser._clear_session_restore_state(str(tmp_path))

    assert (default_dir / "Cookies").read_bytes() == b"real cookies db"
    assert (default_dir / "Login Data").read_bytes() == b"real login data"


def test_clear_session_restore_state_is_a_noop_when_nothing_to_clear(tmp_path):
    # No Default/Sessions dir at all — first-ever launch with a brand new profile.
    browser._clear_session_restore_state(str(tmp_path / "does-not-exist"))


class _FakePageWithPid:
    def __init__(self, process_id: int) -> None:
        self.process_id = process_id


def test_forget_page_discards_the_process_id():
    browser._active_pids.add(999999)
    browser.forget_page(_FakePageWithPid(999999))

    assert 999999 not in browser._active_pids


def test_forget_page_is_a_noop_for_an_untracked_pid():
    browser.forget_page(_FakePageWithPid(123456))  # must not raise


def test_kill_all_browsers_kills_a_real_tracked_process():
    # The "Cancelar" button's safety net (server.py's /cancel) — needs a
    # genuine OS-level kill to matter, so this spawns (and cleans up) a real
    # short-lived process rather than mocking os.kill.
    proc = subprocess.Popen(["sleep", "30"])
    browser._active_pids.add(proc.pid)
    try:
        browser.kill_all_browsers()
        proc.wait(timeout=2)
        assert proc.returncode is not None
    finally:
        browser._active_pids.discard(proc.pid)
        proc.kill()
        proc.wait()


def test_kill_all_browsers_skips_an_already_dead_pid():
    proc = subprocess.Popen(["true"])
    proc.wait()  # already exited before kill_all_browsers ever sees it
    browser._active_pids.add(proc.pid)
    try:
        browser.kill_all_browsers()  # must not raise
    finally:
        browser._active_pids.discard(proc.pid)


def test_start_cancellation_watcher_sets_giveup_once_cancellation_requested():
    giveup = threading.Event()
    browser.start_cancellation_watcher(giveup)
    cancellation.request()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not giveup.is_set():
        time.sleep(0.05)

    assert giveup.is_set() is True


def test_start_cancellation_watcher_never_sets_giveup_without_a_cancellation():
    giveup = threading.Event()
    browser.start_cancellation_watcher(giveup)

    time.sleep(0.2)

    assert giveup.is_set() is False
    giveup.set()  # let the watcher thread exit instead of leaking
