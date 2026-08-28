"""Collector framework: shared contract + plumbing every source plugs into.

Site-specific collectors (occ, computrabajo, ...) are built in EATP-004-008
on top of `base.py` / `http.py`. `hireline.py`, `weremoto.py`,
`remotojob.py` (EATP-030) follow the same HTTP-only shape, discovered via
sitemap/category pages instead of a search API.
"""

from __future__ import annotations

from rove.collectors.base import CollectorRegistry
from rove.collectors.computrabajo import ComputrabajoCollector
from rove.collectors.greenhouse import GreenhouseCollector
from rove.collectors.himalayas import HimalayasCollector
from rove.collectors.hireline import HirelineCollector
from rove.collectors.lever import LeverCollector
from rove.collectors.occ import OCCCollector
from rove.collectors.remoteok import RemoteOKCollector
from rove.collectors.remotive import RemotiveCollector
from rove.collectors.remotojob import RemotoJobCollector
from rove.collectors.weremoto import WeremotoCollector
from rove.collectors.wwr import WWRCollector

# Sources that drive a real Chromium browser — slower, and carrying real
# account/block risk (P23). The orchestrator's 'fast' mode (EATP-014) drops
# these; 'thorough' (the default) keeps them for full coverage. Empty since
# EATP-033 (Indeed removed — Kevin's call, unattended captcha volume made it
# unworkable; LinkedIn was the other member, removed in EATP-027). Kept as a
# live mechanism, not deleted, for whichever future source needs it — until
# then 'fast' and 'thorough' run the same set.
BROWSER_SOURCES: set[str] = set()


def build_registry() -> CollectorRegistry:
    """The real registry, wired to every live collector (EATP-004-008). Tests
    build their own registry with fakes instead of calling this."""
    registry = CollectorRegistry()
    registry.register("occ", OCCCollector)
    registry.register("computrabajo", ComputrabajoCollector)
    registry.register("remotive", RemotiveCollector)
    registry.register("wwr", WWRCollector)
    registry.register("remoteok", RemoteOKCollector)
    registry.register("himalayas", HimalayasCollector)
    registry.register("greenhouse", GreenhouseCollector)
    registry.register("lever", LeverCollector)
    registry.register("hireline", HirelineCollector)
    registry.register("weremoto", WeremotoCollector)
    registry.register("remotojob", RemotoJobCollector)
    return registry
