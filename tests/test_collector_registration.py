"""Confirms OCC and Computrabajo satisfy the shared `Collector` protocol and
slot into the EATP-003 registry. Site-specific parsing is tested in their own
files; this only proves the wiring works.
"""

from __future__ import annotations

import httpx
import pytest

from rove import config
from rove.collectors.base import Collector, CollectorRegistry, CollectorStatus
from rove.collectors.computrabajo import ComputrabajoCollector
from rove.collectors.occ import OCCCollector


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("rove.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def _client_returning_404() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))


def test_occ_and_computrabajo_satisfy_the_collector_protocol():
    assert isinstance(OCCCollector(client=_client_returning_404()), Collector)
    assert isinstance(ComputrabajoCollector(client=_client_returning_404()), Collector)


def test_both_register_and_run_through_the_registry(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    registry = CollectorRegistry()
    registry.register("occ", lambda: OCCCollector(client=_client_returning_404()))
    registry.register("computrabajo", lambda: ComputrabajoCollector(client=_client_returning_404()))

    assert set(registry.enabled_names()) == {"occ", "computrabajo"}

    results = registry.run_enabled()

    assert set(results) == {"occ", "computrabajo"}
    for source, (jobs, result) in results.items():
        assert jobs == []
        assert result.source == source
        # A failed search request means "no real results this page" — the
        # registry's envelope, not a crash (EATP-003's whole point).
        assert result.status == CollectorStatus.EMPTY
