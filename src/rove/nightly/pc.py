"""The real outside world for the nightly runner, on Kevin's PC (WSL side, EATP-037).

Everything here is a thin shell over something that already exists: the
`claude` CLI (Sonnet, driving his real Chrome through the extension), two
PowerShell helpers in `pc/nightly/`, the Vigilante project's keep-awake script
and its Home Assistant config for phone notices, and Windows' own `shutdown /h`.
`runner.py` only ever sees these through `Ports`, so none of it runs in tests.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx

from rove import config
from rove.nightly import answers as answers_mod
from rove.nightly.client import RoveClient
from rove.nightly.quota import Quota, parse_quota, parse_quota_error
from rove.nightly.runner import ClaudeResult, Ports, RunConfig

logger = logging.getLogger("rove.nightly.pc")

PC_SCRIPTS = Path(__file__).resolve().parents[3] / "pc" / "nightly"
VIGILANTE_DIR = Path(os.getenv("VIGILANTE_DIR", "/mnt/d/Development/Vigilante"))
VIGILANTE_CONFIG = Path(os.getenv("VIGILANTE_CONFIG", str(Path.home() / ".config" / "vigilante" / "config")))
# `claude -p` must NOT run inside the Rove checkout: it would load this repo's
# CLAUDE.md (the EATP operating contract) into a session that only applies to jobs.
WORK_DIR = Path(os.getenv("ROVE_NIGHTLY_WORKDIR", str(Path.home() / "rove-nightly-work")))
CLAUDE_BIN = os.getenv("CLAUDE_BIN", str(Path.home() / ".local" / "bin" / "claude"))
POWERSHELL = "powershell.exe"
SHUTDOWN = "/mnt/c/Windows/System32/shutdown.exe"
CLAUDE_TOOLS = "mcp__claude-in-chrome"


def _win(path: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, check=True).stdout.strip()


def _run_ps(script: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _win(script), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# --- quota ------------------------------------------------------------------


MAX_RETRY_AFTER = 330  # seconds; longer than this and waiting is not worth it


def read_quota(*, attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> Quota | None:
    """Read the usage, retrying a rate limit (HTTP 429 asks to wait `Retry-After`
    seconds) or a blip a few times. Still fails closed: `None` after the last try."""
    for attempt in range(attempts):
        try:
            completed = _run_ps(PC_SCRIPTS / "read_quota.ps1", timeout=45)
            reading = parse_quota(completed.stdout)
            if reading is not None:
                return reading
            status, retry_after = parse_quota_error(completed.stdout)
        except (OSError, subprocess.SubprocessError):
            status, retry_after = 0, 0
        if attempt == attempts - 1:
            break
        if status == 429 and retry_after <= MAX_RETRY_AFTER:
            sleep(retry_after + 3)
        elif status == 429:
            return None
        else:
            sleep(15)
    return None


# --- Claude -----------------------------------------------------------------


def run_claude(prompt: str, *, model: str = "sonnet", max_turns: int = 120, timeout: int = 2400) -> ClaudeResult:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        CLAUDE_BIN, "-p", prompt, "--chrome", "--allowedTools", CLAUDE_TOOLS,
        "--model", model, "--max-turns", str(max_turns), "--output-format", "json",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=WORK_DIR)
    except subprocess.TimeoutExpired:
        return ClaudeResult(ok=False, error=f"tiempo agotado ({timeout} s)")
    except OSError as exc:
        return ClaudeResult(ok=False, error=f"no pude lanzar claude: {exc}")
    try:
        data: dict[str, Any] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ClaudeResult(ok=False, error=f"salida ilegible (código {completed.returncode})")
    ok = (not data.get("is_error")) and data.get("subtype") == "success"
    return ClaudeResult(
        ok=ok,
        text=str(data.get("result") or ""),
        error="" if ok else str(data.get("subtype") or "error"),
        cost_usd=data.get("total_cost_usd"),
        turns=data.get("num_turns"),
    )


# --- phone notices (reuses the Vigilante project's Home Assistant config) ----


def _vigilante_config() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in VIGILANTE_CONFIG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw = line.removeprefix("export ").partition("=")
            parts = shlex.split(raw)
            values[key.strip()] = parts[0] if parts else ""
    except (OSError, ValueError):
        pass
    return values


def notify(title: str, message: str) -> None:
    cfg = _vigilante_config()
    try:
        token_path = os.path.expanduser(os.path.expandvars(cfg["TOKEN_FILE"]))
        token = Path(token_path).read_text(encoding="utf-8").strip()
        base, devices = cfg["HA"].rstrip("/"), cfg["NOTIFY_DEVICES"].split()
    except (KeyError, OSError):
        logger.warning("sin configuración de avisos; no pude notificar: %s", title)
        return
    for device in devices:
        with contextlib.suppress(httpx.HTTPError):
            httpx.post(
                f"{base}/api/services/notify/{device}",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": title, "message": message},
                timeout=15,
            )


CHROME_START_WAIT = 30  # seconds for Chrome and the extension to come up after launching it


def ensure_chrome(*, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Start Chrome if it is not running (Kevin's rule: the Claude extension only connects while
    Chrome is open, and he has always fixed it by opening Chrome first). Returns True if it had to
    launch it. Best effort: a failure here just means the batch will fail and be retried."""
    try:
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command",
             "if (Get-Process chrome -ErrorAction SilentlyContinue) { 'running' } else { Start-Process chrome; 'started' }"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if "started" in completed.stdout:
        logger.info("Chrome estaba cerrado: lo abrí; espero %s s a que conecte la extensión", CHROME_START_WAIT)
        sleep(CHROME_START_WAIT)
        return True
    return False


# --- keep the PC awake / let it sleep ----------------------------------------


@contextlib.contextmanager
def keep_awake(minutes: int = 180) -> Iterator[None]:
    script = VIGILANTE_DIR / "scripts" / "mantener-despierto.ps1"
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _win(script), "-Minutos", str(minutes)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("no pude pedir mantener despierto")
    try:
        yield
    finally:
        if process is not None and process.poll() is None:
            process.terminate()


VIGILANTE_STATE_DIR = Path(os.getenv("VIGILANTE_STATE", str(Path.home() / ".cache" / "vigilante")))


def charger_off() -> bool:
    """Turn the laptop's charger (Kevin's smart plug in Home Assistant) off before hibernating,
    like the Vigilante does: Kevin never wants it left on while the PC sleeps. Also leaves the
    Vigilante's `apagando` marker so it does not switch it straight back on. Best effort."""
    cfg = _vigilante_config()
    try:
        token = Path(os.path.expanduser(os.path.expandvars(cfg["TOKEN_FILE"]))).read_text(encoding="utf-8").strip()
        base, switch = cfg["HA"].rstrip("/"), cfg.get("SWITCH", "switch.laptop")
    except (KeyError, OSError):
        logger.warning("sin configuración de Home Assistant: no pude apagar el cargador")
        return False
    try:
        VIGILANTE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        (VIGILANTE_STATE_DIR / "apagando").write_text(str(int(time.time())), encoding="utf-8")
        response = httpx.post(
            f"{base}/api/services/switch/turn_off",
            headers={"Authorization": f"Bearer {token}"},
            json={"entity_id": switch},
            timeout=15,
        )
        return response.status_code == 200
    except (OSError, httpx.HTTPError):
        return False


def hibernate_if_idle(min_idle_minutes: float = 10.0) -> bool:
    """Hibernate (charger off first) only when Windows can prove Kevin has been away; any
    doubt (script failed, unreadable number) means he is present and nothing happens."""
    try:
        completed = _run_ps(PC_SCRIPTS / "idle_minutes.ps1", timeout=30)
        idle = float(completed.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return False
    if idle < min_idle_minutes:
        return False
    charger_off()
    subprocess.run([SHUTDOWN, "/h"], check=False)
    return True


# --- assembly ----------------------------------------------------------------


class _ReadOnlyClient(RoveClient):
    """Dry run: reads are real, every write to Rove is a no-op, and the kill
    switch is ignored (the point is to see what *would* run)."""

    def get_settings(self) -> dict[str, Any]:
        return {**super().get_settings(), "allowed": True, "reason": "dry-run (ignora el interruptor)"}

    def consume_skip(self) -> dict[str, Any]:
        return {}

    def track(self, signature: str, action: str) -> dict[str, Any]:
        return {}

    def add_skipped(self, url: str, reason: str, **fields: str) -> dict[str, Any]:
        return {}

    def add_question(self, question: str, language: str, vacancy: dict[str, str]) -> dict[str, Any]:
        return {}


def real_ports(*, dry_run: bool, cfg: RunConfig) -> Ports:
    if not dry_run:
        return Ports(
            client=RoveClient(),
            read_quota=read_quota,
            run_claude=run_claude,
            notify=notify,
            keep_awake=keep_awake,
            hibernate_if_idle=lambda: hibernate_if_idle(cfg.min_idle_minutes),
            applicant_answers=answers_mod.load_applicant_answers,
            ensure_chrome=ensure_chrome,
        )

    def fake_claude(prompt: str) -> ClaudeResult:
        print(f"[dry-run] prompt de {len(prompt)} caracteres, no se llama a Claude")
        print(prompt[prompt.index("VACANTES:") : prompt.index("FORMATO DE RESPUESTA")])
        return ClaudeResult(ok=True, text='{"outcomes": []}')

    return Ports(
        client=_ReadOnlyClient(),
        read_quota=read_quota,
        run_claude=fake_claude,
        notify=lambda title, message: print(f"[dry-run] aviso: {title} — {message}"),
        keep_awake=contextlib.nullcontext,
        hibernate_if_idle=lambda: False,
        applicant_answers=answers_mod.load_applicant_answers,
        progress_dir=Path(tempfile.mkdtemp(prefix="rove-nightly-dry-")),
    )
