"""career_radar/cancellation.py — the process-wide flag behind the
"Cancelar" button. Pure threading.Event wrapper, tested directly. The
autouse `_reset_cancellation_flag` fixture (conftest.py) keeps this state
from leaking between tests.
"""

from __future__ import annotations

import pytest

from career_radar import cancellation


def test_not_requested_by_default():
    assert cancellation.is_requested() is False


def test_request_sets_the_flag():
    cancellation.request()
    assert cancellation.is_requested() is True


def test_reset_clears_the_flag():
    cancellation.request()
    cancellation.reset()
    assert cancellation.is_requested() is False


def test_check_raises_once_requested():
    cancellation.request()
    with pytest.raises(cancellation.RunCancelled):
        cancellation.check()


def test_check_is_a_noop_when_not_requested():
    cancellation.check()  # must not raise
