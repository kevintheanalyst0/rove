from __future__ import annotations

import pytest

from rove import cancellation
from rove.collectors import browser


@pytest.fixture(autouse=True)
def _no_real_windows_foreground_calls(monkeypatch):
    """`browser.bring_to_front` (EATP-023) shells out to a real
    `powershell.exe` when running on WSL — which this dev box is. Without
    this, every test that exercises `bring_to_front` (directly or through a
    collector) would launch a real Windows process. Default it to a no-op;
    the tests dedicated to `_force_windows_foreground`/`_is_wsl` themselves
    override this locally with their own `monkeypatch.setattr`."""
    monkeypatch.setattr(browser, "_force_windows_foreground", lambda: None)


@pytest.fixture(autouse=True)
def _reset_cancellation_flag():
    """The "Cancelar" button's flag (rove/cancellation.py) is a
    single process-wide `threading.Event` — without this, a test that calls
    `cancellation.request()` (or `/cancel`) would leak a "cancelled" state
    into every test that runs after it in the same pytest process."""
    cancellation.reset()
    yield
    cancellation.reset()
