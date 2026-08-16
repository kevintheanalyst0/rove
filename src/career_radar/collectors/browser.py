"""Stealthier Chromium base for browser-driven collectors (LinkedIn, Indeed).

WSL has no system Chromium package worth trusting (Ubuntu 24.04 only offers
`chromium` as a snap, which sandboxes file access in ways that fight
DrissionPage's custom profile dirs). Instead this resolves to the standalone
binary Playwright downloads (`playwright install chromium`) — no sudo, no
snap confinement, and it's already a project dependency.

Replaces `legacy/jobmatch/collectors/browser.py`'s `alert_manual_intervention`,
which used a terminal beep + `input()`-adjacent blocking flow. Manual steps
(captcha/login) are now surfaced as an event on the shared bus (ADR-004,
R11/R12) — the caller decides how to pause/skip, never this module.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage

from career_radar import config
from career_radar.events import bus

# Realistic, common viewport sizes — a fixed size is itself a fingerprint.
_VIEWPORTS = [(1366, 768), (1440, 900), (1536, 864), (1920, 1080)]


def _find_playwright_chromium() -> str | None:
    """Locate the `chrome` binary Playwright downloaded, if any."""
    cache_dir = Path.home() / ".cache" / "ms-playwright"
    if not cache_dir.exists():
        return None
    candidates = sorted(cache_dir.glob("chromium-*/chrome-linux64/chrome"), reverse=True)
    return str(candidates[0]) if candidates else None


def resolve_chrome_path() -> str | None:
    """Resolution order: explicit config override -> Playwright's bundled Chromium.

    Returns None if neither is found; DrissionPage then falls back to
    whatever `chromium`/`google-chrome` it can find on PATH.
    """
    return config.CHROME_BROWSER_PATH or _find_playwright_chromium()


def _clear_session_restore_state(user_data_dir: str) -> None:
    """Delete Chromium's tab-restore snapshot for the `Default` profile
    (`Sessions/Session_*` and `Sessions/Tabs_*`), leaving cookies/login data
    untouched.

    `ChromiumPage.quit()` (DrissionPage) force-kills the browser process
    right after asking it to close, which routinely wins the race against
    Chrome finishing its own "this was a clean exit" write — every profile
    directory this project has produced was stuck at `exit_type: "Crashed"`
    (checked directly in `Default/Preferences`). Combined with a *shared*
    profile across collectors (Kevin's call, so Indeed/LinkedIn logins both
    persist), Chrome's crash-recovery then restores whatever tabs were open
    last time on the *next* launch — Kevin observed a stray LinkedIn tab
    still open during an Indeed run. Clearing the restore snapshot before
    every launch means each collector always starts with a blank window,
    regardless of how the previous one exited."""
    sessions_dir = Path(user_data_dir) / "Default" / "Sessions"
    if not sessions_dir.exists():
        return
    for entry in sessions_dir.iterdir():
        if entry.is_file():
            entry.unlink(missing_ok=True)


def build_options(*, use_profile: bool = True, headless: bool = False) -> ChromiumOptions:
    """Chromium options with a randomized viewport and a resolved binary path.

    `use_profile=True` reuses the persistent profile dir (session reuse:
    fewer logins, fewer captchas across runs).
    """
    options = ChromiumOptions()

    chrome_path = resolve_chrome_path()
    if chrome_path:
        options.set_browser_path(chrome_path)
    if use_profile:
        options.set_user_data_path(config.CHROME_USER_DATA_DIR)
        _clear_session_restore_state(config.CHROME_USER_DATA_DIR)

    width, height = random.choice(_VIEWPORTS)
    options.set_argument(f"--window-size={width},{height}")
    options.set_argument("--disable-blink-features=AutomationControlled")
    if headless:
        options.headless(True)

    return options


def build_page(
    *, use_profile: bool = True, headless: bool = False, start_minimized: bool = False
) -> ChromiumPage:
    page = ChromiumPage(addr_or_opts=build_options(use_profile=use_profile, headless=headless))
    if not headless:
        if start_minimized:
            # EATP-023 (2026-08-15, Kevin's call): a source that almost never
            # needs him (LinkedIn) or only needs him at one specific moment
            # (Indeed's captcha) shouldn't steal focus on every launch —
            # start minimized, `bring_to_front()` raises it exactly when
            # there's actually something for him to do.
            page.set.window.mini()
        else:
            # Kevin's call (2026-08-13): he needs to read/solve a captcha in
            # this window, so it must be maximized, not whatever small
            # randomized viewport `build_options` picked for fingerprint
            # variety. New tabs share this same OS window, so this covers
            # them too — no per-tab call needed.
            page.set.window.max()
    return page


def bring_to_front(page) -> None:
    """Raise and maximize the (possibly minimized) window — call this
    exactly when Kevin actually needs to look at it (a captcha/login-wall),
    never on every launch.

    EATP-023 first cut only called `.set.window.max()`, which changes the
    shared OS window's *size/state* but not *which tab is showing in it* —
    Kevin reported the window coming forward but reading as a blank page: it
    had raised/resized the window while a different (idle) tab across
    Indeed's detail-fetch pool was still the one selected. `.set.activate()`
    (CDP `Target.activateTarget`) is the actual "select this tab" call;
    `.set.window.max()` alone was never going to show the right content.

    Always maximizes, never just "shows": EATP-019 randomized the viewport
    size for fingerprint variety, and Kevin has hit windows too small to
    read/click in before — a window that's finally asking for his attention
    must never be one of those tiny ones."""
    page.set.activate()
    page.set.window.max()


def human_pause(min_seconds: float = 1.5, max_seconds: float = 4.0) -> None:
    """Randomized pacing between browser actions — slower and less regular
    than the HTTP layer's `gentle_pause`, matching how a person reads a page."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def request_manual_intervention(source: str, message: str) -> None:
    """Publish a `needs_intervention` event instead of blocking on a terminal
    prompt. The web UI (EATP-015/016) surfaces this to Kevin; the caller
    (a browser collector) should stop yielding for this source and let the
    orchestrator (EATP-014) decide whether/when to resume — never wait here.
    """
    bus.publish(
        phase=f"collect:{source}",
        status="needs_intervention",
        message=message,
    )


def clear_manual_intervention(source: str) -> None:
    """Pair to `request_manual_intervention`: tell the web UI the thing it
    asked Kevin to resolve (captcha, login) is actually resolved now.

    EATP-020: without this, Kevin's "resuélvela en la ventana" banner stayed
    on screen indefinitely after he'd already solved it — the frontend only
    ever cleared notices at the *next pipeline phase* (gate/prefilter/ai),
    which could be minutes away or, if this was the last collector, never
    visibly happen before he stopped watching. The caller should publish this
    the moment it detects the block is gone, not wait for anything else.
    """
    bus.publish(
        phase=f"collect:{source}",
        status="intervention_resolved",
        message="",
    )
