from __future__ import annotations

import pytest

from rove import cancellation


@pytest.fixture(autouse=True)
def _reset_cancellation_flag():
    """The "Cancelar" button's flag (rove/cancellation.py) is a
    single process-wide `threading.Event` — without this, a test that calls
    `cancellation.request()` (or `/cancel`) would leak a "cancelled" state
    into every test that runs after it in the same pytest process."""
    cancellation.reset()
    yield
    cancellation.reset()
