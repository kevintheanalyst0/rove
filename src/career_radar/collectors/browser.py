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
from collections.abc import Callable
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
    # EATP-024: WSLg's virtual GPU is unstable enough to lose its
    # compositor context mid-session — reproduced live on this exact box
    # with Chrome's own `--enable-logging`/`--log-file` output: a plain
    # `about:blank` load alone fired `GPU.ContextLost.RendererCompositor`
    # and `GPU.ContextLost.RendererRasterWorker` within seconds (Chrome's
    # own `GPU.BlocklistFeatureTestResults.GpuCompositing` histogram already
    # flags this hardware/driver combo as blocklisted for compositing).
    # `--disable-gpu-compositing` alone (EATP-024's fix) only took the GPU
    # process out of the *compositor* step — it kept running for
    # rasterization and everything else, still talking to the same
    # blocklisted driver. EATP-025 (2026-08-17): two live runs in a row hit
    # a harder failure than context-loss-with-blank-paint — the whole Chrome
    # process died mid-session (confirmed via `ps`: zombie, no other chrome
    # process left at all), hanging LinkedIn's/Indeed's collectors forever
    # (see `run_bounded` below for why "forever" and not "erroring out").
    # `--disable-gpu` removes the GPU process from the picture entirely —
    # Chromium falls back to full software rendering from launch, never
    # touching the driver Chrome's own histogram already distrusts. Slower
    # per-frame, irrelevant for scraping.
    #
    # Worth recording plainly, because it reframes every "legacy did this
    # fine" comparison in this file: **legacy never ran under WSL at all.**
    # Kevin ran it natively on Windows (2026-08-17) — real GPU driver, no
    # WSLg compositor, no virtualized display. So legacy's stability here is
    # not evidence that 4 tabs / headful / this flag set is safe *in WSL*;
    # it's evidence that this whole class of GPU/display instability simply
    # did not exist in the environment legacy ran in. Every collector
    # setting inherited from legacy needs judging against WSL on its own
    # merits, not against legacy's track record on a different platform.
    options.set_argument("--disable-gpu")
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


def close_page(page: ChromiumPage, timeout: float = 20.0) -> None:
    """Shut a collector's browser down without ever being able to hang on it.

    EATP-025: `page.quit()` looked like pure teardown, so it sat in a
    `finally` outside the bounded call — but it opens with the same
    `self._run_cdp('Browser.close')` every other DrissionPage call uses, and
    that call has no timeout either. Against a browser that's already dead
    it blocks forever, exactly like a mid-run `tab.get()` does. That's what
    kept hanging LinkedIn after the collector's own work was already safely
    bounded, and it's why the run's thread never ended even once the
    collecting was done.

    So: try the graceful quit in a thread, give it `timeout`, then SIGKILL
    whatever's left either way. The kill is not a fallback for the timeout
    path only — a `quit()` that *returns* can still leave the process alive
    (its own force-kill is best-effort and silently swallows failures), and
    a leaked Chrome on a 16GB box is precisely the memory pressure that
    starts this whole failure mode over again on the next source.
    """
    pid = None
    try:
        pid = page.process_id
    except Exception:  # noqa: BLE001 - a dead browser may not even report this
        pass

    quitter = threading.Thread(target=lambda: _quiet_quit(page), daemon=True)
    quitter.start()
    quitter.join(timeout=timeout)

    if pid is None:
        return
    try:
        os.kill(pid, 0)
    except OSError:
        pass  # already gone, nothing to clean up
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    with _active_pids_lock:
        _active_pids.discard(pid)


def _quiet_quit(page: ChromiumPage) -> None:
    try:
        page.quit()
    except Exception:  # noqa: BLE001 - teardown must never raise into a collector
        pass


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


# Generous — normal listing/detail-fetch work for a tab pool finishes in
# well under this (linkedin.py's own live numbers: 61-165s for the whole
# 4-tab listing phase). Only a browser that's actually died mid-`func`
# should ever hit it.
_STUCK_WORKER_TIMEOUT_SECONDS = 180.0


def run_bounded(
    func: Callable[[], None],
    giveup: threading.Event,
    source: str,
    timeout: float = _STUCK_WORKER_TIMEOUT_SECONDS,
) -> None:
    """Run `func` in a background thread, but never wait past `timeout`
    total. `func` is expected to accumulate its results into whatever
    mutable structure (dict/Queue/list) the caller already holds a
    reference to, not return a value — that's what lets the caller keep
    whatever partial progress landed even if `func` never finishes.

    EATP-025 (2026-08-17, live, three times): when the Chrome process dies
    mid-session, a thread blocked inside a CDP call waiting for that tab's
    response never wakes up on its own — DrissionPage puts no timeout on
    that specific wait, so it's not an exception the collector could catch,
    just a permanent hang. `giveup.is_set()` checks between iterations can't
    help a thread that's stuck *inside* one such call, and neither can
    cooperative cancellation (confirmed live: `/cancel` sat for 20+ seconds
    with the run still "running" and the dead Chrome still unreaped).

    First cut of this backstop only wrapped the final `thread.join()` of an
    already-running tab-worker pool — still hung a third time, because
    opening that pool's *own* tabs (`new_tab()`, called synchronously by the
    caller before any worker thread exists) is just as capable of blocking
    forever on a dead browser as anything the workers themselves do
    afterward. Wrapping the entire call — tab setup, worker spawn, and
    their join, whatever `func` actually contains — closes that gap: no CDP
    call anywhere inside a collector's browser-touching work can hang the
    run past `timeout`, regardless of which one it happens to be this time.

    This is the backstop, not the fix — the actual prevention is
    `--disable-gpu` in `build_options` above (removes the driver that's
    been dying) plus keeping the browser's own memory footprint down
    (fewer parallel tabs). This just guarantees a hard ceiling on the
    damage if the browser dies anyway: past `timeout`, stop waiting and set
    `giveup` so every other in-flight thread for this `collect()` call winds
    down too. The abandoned thread (and anything it started) is never
    killed, just left running — Python has no way to force-kill a thread —
    harmless, since it dies with the process regardless.
    """
    thread = threading.Thread(target=func, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        giveup.set()
        bus.publish(
            phase=f"collect:{source}",
            status="degraded",
            message=f"{source}: el navegador dejó de responder; se omite el resto de esta fuente.",
        )


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
