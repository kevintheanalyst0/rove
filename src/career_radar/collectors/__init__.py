"""Collector framework: shared contract + plumbing every source plugs into.

Site-specific collectors (occ, computrabajo, linkedin, indeed, ...) are built
in EATP-004-008 on top of `base.py` / `http.py` / `browser.py`.
"""

from __future__ import annotations

from career_radar.collectors.base import CollectorRegistry
from career_radar.collectors.computrabajo import ComputrabajoCollector
from career_radar.collectors.greenhouse import GreenhouseCollector
from career_radar.collectors.himalayas import HimalayasCollector
from career_radar.collectors.indeed import IndeedCollector
from career_radar.collectors.lever import LeverCollector
from career_radar.collectors.linkedin import LinkedInCollector
from career_radar.collectors.occ import OCCCollector
from career_radar.collectors.remoteok import RemoteOKCollector
from career_radar.collectors.remotive import RemotiveCollector
from career_radar.collectors.wwr import WWRCollector

# Sources that drive a real Chromium browser (DrissionPage) — slower, and the
# ones carrying real account/block risk (P23). The orchestrator's 'fast' mode
# (EATP-014) drops these; 'thorough' (the default) keeps them for full
# coverage.
BROWSER_SOURCES = {"linkedin", "indeed"}


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
    registry.register("linkedin", LinkedInCollector)
    registry.register("indeed", IndeedCollector)
    return registry
