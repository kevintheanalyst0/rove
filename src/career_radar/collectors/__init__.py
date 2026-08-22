"""Collector framework: shared contract + plumbing every source plugs into.

Site-specific collectors (occ, computrabajo, indeed, ...) are built in
EATP-004-008 on top of `base.py` / `http.py` / `browser.py`. `hireline.py`,
`weremoto.py`, `remotojob.py` (EATP-030) follow the same HTTP-only shape,
discovered via sitemap/category pages instead of a search API.
"""

from __future__ import annotations

from career_radar.collectors.base import CollectorRegistry
from career_radar.collectors.computrabajo import ComputrabajoCollector
from career_radar.collectors.greenhouse import GreenhouseCollector
from career_radar.collectors.himalayas import HimalayasCollector
from career_radar.collectors.hireline import HirelineCollector
from career_radar.collectors.indeed import IndeedCollector
from career_radar.collectors.lever import LeverCollector
from career_radar.collectors.occ import OCCCollector
from career_radar.collectors.remoteok import RemoteOKCollector
from career_radar.collectors.remotive import RemotiveCollector
from career_radar.collectors.remotojob import RemotoJobCollector
from career_radar.collectors.weremoto import WeremotoCollector
from career_radar.collectors.wwr import WWRCollector

# Sources that drive a real Chromium browser (DrissionPage) — slower, and
# carrying real account/block risk (P23). The orchestrator's 'fast' mode
# (EATP-014) drops these; 'thorough' (the default) keeps them for full
# coverage. LinkedIn used to be in this set too; removed entirely in EATP-027
# (fragile for its yield — see ROADMAP.md P26), not just dropped from here.
BROWSER_SOURCES = {"indeed"}


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
    registry.register("indeed", IndeedCollector)
    return registry
