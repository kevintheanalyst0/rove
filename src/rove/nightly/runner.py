"""The nightly run, as plain orchestration code (EATP-037).

Everything that costs tokens is one `claude -p` batch; everything else —
reading Kevin's switch, reading his quota, choosing vacancies, writing the
outcomes to Rove, the progress log, the phone summary, hibernating — is code
in this file and spends none. Every outside effect is an injected port, so the
whole flow is tested with fakes and no live Claude.

Fails closed: switch unreadable, quota unreadable, quota too high -> it does not
run and tells Kevin. A batch that errors marks nothing in Rove (its vacancies
stay in the inbox for another night).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ContextManager

import httpx

from rove import config
from rove.nightly import answers as answers_mod
from rove.nightly import selector
from rove.nightly.client import RoveClient
from rove.nightly.outcomes import Outcome, Recorded, parse_batch_result, record_outcomes
from rove.nightly.prompt import build_batch_prompt
from rove.nightly.quota import Quota

logger = logging.getLogger("rove.nightly.runner")


@dataclass(frozen=True)
class RunConfig:
    max_per_night: int = 20
    batch_size: int = 4
    session_stop_pct: float = 90.0
    mass_threshold: int = selector.MASS_POSTER_THRESHOLD
    max_consecutive_failures: int = 2
    min_idle_minutes: float = 10.0


@dataclass(frozen=True)
class ClaudeResult:
    ok: bool
    text: str = ""
    error: str = ""
    cost_usd: float | None = None
    turns: int | None = None


@dataclass
class Ports:
    client: RoveClient
    read_quota: Callable[[], Quota | None]
    run_claude: Callable[[str], ClaudeResult]
    notify: Callable[[str, str], None]
    keep_awake: Callable[[], ContextManager[None]]
    hibernate_if_idle: Callable[[], bool]
    applicant_answers: Callable[[], dict[str, Any]]
    # Make sure Chrome (with Kevin's Claude extension) is running before a batch needs it.
    ensure_chrome: Callable[[], None] = lambda: None
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    progress_dir: Path = field(default_factory=lambda: config.NIGHTLY_PROGRESS_DIR)


@dataclass
class RunReport:
    status: str  # ran | off | skipped | no_switch | no_quota | weekly_cap | nothing_to_do
    detail: str = ""
    attempted: int = 0
    applied: int = 0
    dismissed: int = 0
    for_kevin: int = 0
    questions: int = 0
    pending: int = 0
    batches: int = 0
    failures: int = 0
    stop_reason: str = ""
    quota_start: Quota | None = None
    quota_end: Quota | None = None
    summary: str = ""
    errors: list[str] = field(default_factory=list)


def may_start_batch(quota: Quota, weekly_cap_pct: float, cfg: RunConfig) -> tuple[bool, str]:
    if quota.weekly_pct >= weekly_cap_pct:
        return False, f"uso semanal {quota.weekly_pct:g} % (tope {weekly_cap_pct:g} %)"
    if quota.session_pct >= cfg.session_stop_pct:
        return False, f"ventana de 5 h al {quota.session_pct:g} %"
    return True, ""


def _progress_path(ports: Ports) -> Path:
    local_day = ports.now().astimezone(config.KEVIN_TIMEZONE).date().isoformat()
    return ports.progress_dir / f"{local_day}.jsonl"


def _processed_tonight(path: Path) -> set[str]:
    done: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("status") != "pending":
                done.add(entry.get("url", ""))
    return done


def _append_progress(path: Path, ports: Ports, candidates: dict[str, selector.Candidate], outcomes: list[Outcome]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for outcome in outcomes:
            candidate = candidates.get(outcome.url)
            handle.write(
                json.dumps(
                    {
                        "at": ports.now().isoformat(),
                        "url": outcome.url,
                        "title": candidate.title if candidate else "",
                        "company": candidate.company if candidate else "",
                        "status": outcome.status,
                        "reason": outcome.reason.value if outcome.reason else None,
                        "evidence": outcome.evidence,
                        "note": outcome.note,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def build_summary(report: RunReport) -> str:
    parts = [f"{report.applied} enviadas"]
    parts.append(f"{report.for_kevin} para ti")
    if report.questions:
        parts.append(f"{report.questions} preguntas nuevas")
    if report.dismissed:
        parts.append(f"{report.dismissed} descartadas")
    if report.pending:
        parts.append(f"{report.pending} sin terminar")
    text = "Corrida nocturna: " + " · ".join(parts) + "."
    if report.quota_start and report.quota_end:
        text += (
            f" Cuota: ventana {report.quota_start.session_pct:g}→{report.quota_end.session_pct:g} %,"
            f" semanal {report.quota_start.weekly_pct:g}→{report.quota_end.weekly_pct:g} %."
        )
    if report.stop_reason:
        text += f" Paré: {report.stop_reason}."
    if report.errors:
        text += f" Con {len(report.errors)} error(es) al anotar en Rove."
    return text


def _run_batches(ports: Ports, cfg: RunConfig, weekly_cap: float, quota: Quota) -> RunReport:
    """Inputs, selection and the batch loop. Runs inside the keep-awake window;
    never notifies or hibernates (the caller does, after releasing it)."""
    report = RunReport(status="ran", quota_start=quota, quota_end=quota)
    try:
        inbox = ports.client.get_inbox()
    except httpx.HTTPError as exc:
        return RunReport(status="no_inbox", detail=str(exc), quota_start=quota, quota_end=quota)
    retry_urls: list[str] = []
    learned: list[dict[str, Any]] = []
    skipped_urls: set[str] = set()
    with contextlib.suppress(httpx.HTTPError):
        retry_urls = ports.client.get_retry_urls()
    with contextlib.suppress(httpx.HTTPError):
        learned = ports.client.get_learned_answers()
    with contextlib.suppress(httpx.HTTPError):
        skipped_urls = ports.client.get_open_skipped_urls()
    with contextlib.suppress(httpx.HTTPError):
        # Waiting on a question Kevin has not answered: trying again tonight would only re-ask it.
        skipped_urls = skipped_urls | ports.client.get_open_question_urls()

    progress = _progress_path(ports)
    candidates = selector.candidates_from_inbox(
        inbox,
        mass_threshold=cfg.mass_threshold,
        exclude_urls=skipped_urls | _processed_tonight(progress),
        retry_urls=retry_urls,
    )
    if not candidates:
        return RunReport(status="nothing_to_do", quota_start=quota, quota_end=quota)

    answers_text = answers_mod.render_for_prompt(ports.applicant_answers(), learned)
    by_url = {c.url: c for c in candidates}
    queue = list(candidates)
    consecutive_failures = 0
    ports.ensure_chrome()  # after a restart (a Windows update, say) Chrome is closed and Claude cannot see the extension

    while queue and report.attempted < cfg.max_per_night:
        # The usage endpoint rate-limits: reuse the preflight reading for the first batch
        # (it was taken seconds ago) and only read again between batches.
        current = quota if report.batches == 0 else ports.read_quota()
        if current is None:
            report.stop_reason = "no pude leer la cuota a mitad de la corrida"
            break
        report.quota_end = current
        allowed, why = may_start_batch(current, weekly_cap, cfg)
        if not allowed:
            report.stop_reason = why
            break
        size = min(cfg.batch_size, cfg.max_per_night - report.attempted, len(queue))
        batch, queue = queue[:size], queue[size:]
        report.batches += 1
        report.attempted += len(batch)

        try:
            result = ports.run_claude(build_batch_prompt(batch, answers_text))
        except Exception as exc:  # a crashing port must not lose the night
            result = ClaudeResult(ok=False, error=f"{type(exc).__name__}: {exc}")
        outcomes = parse_batch_result(result.text, [c.url for c in batch])
        if not result.ok:
            # The session died (turn limit, crash, timeout). It may still have sent some
            # applications and reported them: record what is confirmed so nothing is
            # applied twice tomorrow, and count the batch as a failure.
            report.failures += 1
            consecutive_failures += 1
            report.errors.append(f"lote {report.batches}: {result.error or 'falló'}")
            ports.ensure_chrome()  # maybe Chrome closed mid-run: make sure it is back before the next batch
            salvage = [o for o in outcomes if o.status != "pending"]
            if salvage:
                salvaged = record_outcomes(ports.client, by_url, salvage)
                _append_progress(progress, ports, by_url, salvage)
                report.applied += len(salvaged.applied)
                report.dismissed += len(salvaged.dismissed)
                report.for_kevin += len(salvaged.for_kevin)
                report.questions += len(salvaged.questions)
                report.errors += salvaged.errors
            report.pending += len(batch) - len(salvage)
            if consecutive_failures >= cfg.max_consecutive_failures:
                report.stop_reason = "dos lotes seguidos fallaron"
                break
            continue
        consecutive_failures = 0

        recorded: Recorded = record_outcomes(ports.client, by_url, outcomes)
        _append_progress(progress, ports, by_url, outcomes)
        report.applied += len(recorded.applied)
        report.dismissed += len(recorded.dismissed)
        report.for_kevin += len(recorded.for_kevin)
        report.questions += len(recorded.questions)
        report.pending += len(recorded.pending)
        report.errors += recorded.errors

    if not report.stop_reason:
        report.stop_reason = (
            f"llegué al tope de {cfg.max_per_night} vacantes"
            if report.attempted >= cfg.max_per_night
            else "se acabaron las vacantes elegibles"
        )
    final = ports.read_quota()
    if final is not None:
        report.quota_end = final
    return report


def _run_night(ports: Ports, cfg: RunConfig) -> RunReport:
    # 1. Kevin's switch — fail closed.
    try:
        settings = ports.client.get_settings()
    except httpx.HTTPError as exc:
        ports.notify("Corrida nocturna", "No pude leer el interruptor en Rove: no corrí esta noche.")
        return RunReport(status="no_switch", detail=str(exc))
    if not settings.get("allowed"):
        if settings.get("skip_next_run"):
            with contextlib.suppress(httpx.HTTPError):
                ports.client.consume_skip()
            return RunReport(status="skipped", detail=str(settings.get("reason", "")))
        return RunReport(status="off", detail=str(settings.get("reason", "")))
    weekly_cap = float(settings.get("weekly_cap_pct", 70))

    # 2. Quota — fail closed.
    quota = ports.read_quota()
    if quota is None:
        ports.notify("Corrida nocturna", "No pude leer tu cuota de Claude: no corrí esta noche.")
        return RunReport(status="no_quota")
    allowed, why = may_start_batch(quota, weekly_cap, cfg)
    if not allowed:
        ports.notify("Corrida nocturna", f"No corrí: {why}.")
        return RunReport(status="weekly_cap", detail=why, quota_start=quota, quota_end=quota)

    # 3. The work, with the PC held awake.
    with ports.keep_awake():
        report = _run_batches(ports, cfg, weekly_cap, quota)

    # 4. Tell Kevin, then let the PC sleep (only if he is not using it).
    if report.status == "ran":
        report.summary = build_summary(report)
        ports.notify("Corrida nocturna terminada", report.summary)
    elif report.status == "nothing_to_do":
        ports.notify("Corrida nocturna", "No había vacantes nuevas que aplicar esta noche.")
    elif report.status == "no_inbox":
        ports.notify("Corrida nocturna", "No pude leer la bandeja de Rove: no corrí esta noche.")
    return report


def run_night(ports: Ports, cfg: RunConfig = RunConfig()) -> RunReport:
    report = _run_night(ports, cfg)
    # Whatever happened (ran, switch off, nothing to do, a failure): a PC that woke up for this task goes
    # back to sleep, charger off first (the charging window is only there to let it wake). If Kevin is
    # using the PC, `hibernate_if_idle` does nothing.
    ports.hibernate_if_idle()
    return report


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI over pc.py
    parser = argparse.ArgumentParser(description="Rove nightly apply runner (EATP-037)")
    parser.add_argument("--dry-run", action="store_true", help="read switch/quota/inbox, show what would run; no Claude, no writes")
    parser.add_argument("--max", type=int, default=RunConfig.max_per_night, help="max vacancies this run")
    parser.add_argument("--batch", type=int, default=RunConfig.batch_size, help="vacancies per Claude session")
    parser.add_argument("--no-hibernate", action="store_true", help="never hibernate at the end (supervised runs)")
    args = parser.parse_args(argv)
    from rove.nightly import pc

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = RunConfig(max_per_night=args.max, batch_size=args.batch)
    ports = pc.real_ports(dry_run=args.dry_run, cfg=cfg)
    if args.no_hibernate:
        ports.hibernate_if_idle = lambda: False
    report = run_night(ports, cfg)
    logger.info("status=%s detail=%s summary=%s", report.status, report.detail, report.summary)
    print(report.summary or f"{report.status}: {report.detail}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
