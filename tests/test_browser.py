"""collectors/browser.py — pure filesystem logic only (no real Chromium here;
that's exercised live, never in CI/tests, per CLAUDE.md golden rule 3/8)."""

from __future__ import annotations

from career_radar.collectors import browser


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
