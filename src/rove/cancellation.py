"""Cooperative cancellation for an in-progress pipeline run — the
"Pausar" button (Kevin's request, 2026-08-16, after a run got stuck with
its browser dead and no way to stop it from the UI).

A single process-wide flag. `pipeline.run()` resets it at the start of every
run (so a stale request from a previous run can never silently cancel the
next one) and checks it between stages; the browser collectors' own
existing give-up switches (`_CaptchaCoordination`/`_LoginCoordination`,
already there for captcha/login timeouts) pick it up too, so cancelling
during a captcha wait is as fast as a normal timeout.

EATP-024: a second flag, `discard`, distinguishes "Pausar" (stop, keep the
checkpoint so the next run resumes) from the new "Cancelar" (stop AND throw
the checkpoint away, so the next run starts genuinely fresh). Both still
share the same stop mechanism above — `discard` only changes what
`pipeline.run()`'s `RunCancelled` handler does with the checkpoint once
stopped.
"""

from __future__ import annotations

import threading

_event = threading.Event()
_discard_event = threading.Event()


class RunCancelled(Exception):
    """Raised to unwind a run once cancellation has been requested."""


def reset() -> None:
    _event.clear()
    _discard_event.clear()


def request(*, discard: bool = False) -> None:
    _event.set()
    if discard:
        _discard_event.set()


def is_requested() -> bool:
    return _event.is_set()


def is_discard_requested() -> bool:
    return _discard_event.is_set()


def check() -> None:
    """Raise `RunCancelled` if a cancellation is pending — call this at
    natural stage/iteration boundaries."""
    if _event.is_set():
        raise RunCancelled
