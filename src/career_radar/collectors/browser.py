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

    width, height = random.choice(_VIEWPORTS)
    options.set_argument(f"--window-size={width},{height}")
    options.set_argument("--disable-blink-features=AutomationControlled")
    if headless:
        options.headless(True)

    return options


def build_page(*, use_profile: bool = True, headless: bool = False) -> ChromiumPage:
    return ChromiumPage(addr_or_opts=build_options(use_profile=use_profile, headless=headless))


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
