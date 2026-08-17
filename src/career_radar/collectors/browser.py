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

import os
import random
import signal
import subprocess
import threading
import time
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage

from career_radar import cancellation, config
from career_radar.events import bus

# Realistic, common viewport sizes — a fixed size is itself a fingerprint.
_VIEWPORTS = [(1366, 768), (1440, 900), (1536, 864), (1920, 1080)]

# A string no real page will ever produce on its own, used to find the
# automation Chrome window from the Windows side (see
# `_force_windows_foreground`) without risk of matching some unrelated
# window Kevin happens to have open — a real past failure mode (EATP-023):
# the captcha tab's own title was sometimes a generic "New Tab".
_FOCUS_TITLE_MARKER = "CareerRadar-NeedsAttention"

# PowerShell, run via WSL interop: finds the visible top-level window whose
# title contains the marker and forces it to the foreground.
#
# A plain `SetForegroundWindow` call from an unrelated process (powershell.exe
# here, not the process that owns the target window) is normally silently
# blocked by Windows' foreground-lock — it only honors a focus change coming
# from a process the user just interacted with. The standard workaround is a
# synthetic Alt keypress (`keybd_event`) immediately before the call, which
# Windows treats as evidence of user-driven input and grants the exception.
_FOCUS_PS_SCRIPT = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class CRFocus {{
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc proc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
}}
"@
$target = [IntPtr]::Zero
$proc = {{
    param($hWnd, $lParam)
    if ([CRFocus]::IsWindowVisible($hWnd)) {{
        $len = [CRFocus]::GetWindowTextLength($hWnd)
        if ($len -gt 0) {{
            $sb = New-Object System.Text.StringBuilder ($len + 1)
            [CRFocus]::GetWindowText($hWnd, $sb, $sb.Capacity) | Out-Null
            if ($sb.ToString().Contains("{_FOCUS_TITLE_MARKER}")) {{
                $script:target = $hWnd
                return $false
            }}
        }}
    }}
    return $true
}}
[CRFocus]::EnumWindows($proc, [IntPtr]::Zero) | Out-Null
if ($target -ne [IntPtr]::Zero) {{
    [CRFocus]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
    [CRFocus]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
    [CRFocus]::ShowWindow($target, 9) | Out-Null
    [CRFocus]::SetForegroundWindow($target) | Out-Null
}}
"""


def _is_wsl(proc_version_path: Path = Path("/proc/version")) -> bool:
    try:
        return "microsoft" in proc_version_path.read_text().lower()
    except OSError:
        return False


def _force_windows_foreground() -> None:
    """Best-effort: ask Windows itself (via `powershell.exe`, reachable from
    WSL through interop) to raise the automation Chrome window.

    Exists because the automation Chrome is a native Linux process forwarded
    to Windows through WSLg — `bring_to_front`'s CDP calls (`.set.activate()`,
    `.set.window.*`) only reach Chromium's own internal state, not the Win32
    window WSLg forwards it to. Kevin's live tests (2026-08-16, EATP-023)
    showed those CDP-only calls don't reliably raise/repaint that window.
    Unverified outside a live WSL/Windows run — this is the next thing for
    Kevin to confirm. Swallows all errors: a missing/stuck `powershell.exe`
    must never break the actual captcha-wait flow, only the "please look at
    this" nicety."""
    if not _is_wsl():
        return
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _FOCUS_PS_SCRIPT],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):  # noqa: BLE001 - best-effort nicety, never fatal
        pass


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


_active_pids: set[int] = set()
_active_pids_lock = threading.Lock()


def forget_page(page: ChromiumPage) -> None:
    """Call this alongside `page.quit()` once a collector is done with a
    page — keeps `kill_all_browsers`'s registry from growing forever across
    a long-lived server process (Kevin restarts the app rarely, not once per
    run)."""
    with _active_pids_lock:
        _active_pids.discard(page.process_id)


def kill_all_browsers() -> None:
    """Force-kill every browser process this module has launched and not
    yet `forget_page`-d — the safety net the "Cancelar" button (server.py's
    `/cancel`) falls back on for a collector genuinely stuck *inside* a
    single blocking CDP call, which a cooperative cancellation check between
    iterations can't interrupt. `os.kill(pid, 0)` first, so an already-dead
    PID (the common case — most cancels land between calls, not inside one)
    is skipped instead of risking a signal to some unrelated process that
    reused the number; the tiny remaining race (PID reused in between that
    liveness check and the SIGKILL) is an accepted, low-stakes tradeoff for
    a personal tool a single user clicks a few times a day, not a
    multi-tenant server."""
    with _active_pids_lock:
        pids = list(_active_pids)
    for pid in pids:
        try:
            os.kill(pid, 0)
        except OSError:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def start_cancellation_watcher(giveup: threading.Event) -> None:
    """Starts a daemon thread that sets `giveup` the moment a process-wide
    cancellation is requested (`career_radar.cancellation`, the "Cancelar"
    button) — mirrors it onto a collector's own give-up switch for free, so
    every existing `giveup.is_set()` check (a captcha/login wait's poll
    loop, the tab worker loops) doubles as a cancellation check with no
    other code changes needed. Exits on its own once `giveup` is set, for
    any reason (a real timeout or this same watcher)."""

    def _watch() -> None:
        while not giveup.is_set():
            if cancellation.is_requested():
                giveup.set()
                return
            time.sleep(0.5)

    threading.Thread(target=_watch, daemon=True).start()


def build_page(
    *, use_profile: bool = True, headless: bool = False, start_minimized: bool = False
) -> ChromiumPage:
    page = ChromiumPage(addr_or_opts=build_options(use_profile=use_profile, headless=headless))
    with _active_pids_lock:
        _active_pids.add(page.process_id)
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
    must never be one of those tiny ones.

    Second round (Kevin, live, 2026-08-16): even with `.set.activate()`
    added, the window's frame/outline appeared but its content never
    painted — reading as empty — until he manually clicked it. That's not a
    wrong-tab problem, it's WSLg's compositor apparently not repainting the
    window after a state change made purely over CDP, without any real
    input event. A genuine bounds change (maximized -> normal -> maximized,
    not just resending "maximized") is a common nudge for exactly this class
    of stale-render bug on remote/virtualized displays.

    Third round (Kevin, live, 2026-08-16): the repaint-nudge still didn't
    bring the window forward for a real captcha. All calls so far only ever
    reached Chromium's own internal notion of focus over CDP — none of them
    actually asked *Windows* (which owns the real, WSLg-forwarded Win32
    window) to raise it. Added `_force_windows_foreground`, which does that
    directly via `powershell.exe`/user32.dll. **Still experimental** — can't
    be verified visually from inside WSL; ask Kevin to confirm live."""
    try:
        page.run_js(f"document.title = {_FOCUS_TITLE_MARKER!r};")
    except Exception:  # noqa: BLE001 - best-effort marker, never fatal
        pass
    page.set.activate()
    page.set.window.max()
    time.sleep(0.3)
    page.set.window.normal()
    time.sleep(0.2)
    page.set.window.max()
    _force_windows_foreground()


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
