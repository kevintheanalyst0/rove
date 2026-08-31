"""Central configuration — the single source of truth.

Paths, search terms, and tunables used to be scattered across the legacy
collectors (see `legacy/jobmatch/config.py`). Every later project reads its
settings from here instead of hardcoding them locally.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
HISTORY_DIR = DATA_DIR / "history"
HEALTH_DIR = DATA_DIR / "health"

GATED_FILE = DATA_DIR / "gated.jsonl"
RESULTS_FILE = DATA_DIR / "results.json"
STATUS_FILE = DATA_DIR / "status.json"
SIGNATURES_FILE = CACHE_DIR / "signatures.jsonl"

# Kevin's applied/dismissed actions (EATP-016, ADR-007) — append-only, latest
# action per signature wins (rove.tracking.store).
TRACKING_FILE = DATA_DIR / "tracking.jsonl"

# EATP-031: accumulated inbox — every job that ever cleared the quality gate,
# kept until Kevin applies or dismisses it (rove.inbox.store). Append-only,
# same crash-safety discipline as TRACKING_FILE/history above. Deliberately
# separate from RESULTS_FILE (which stays "last run only", for the run
# diagnostics sidebar) and from TRACKING_FILE (Kevin's decisions, which
# outlive any single job's time in the inbox).
INBOX_FILE = DATA_DIR / "inbox.jsonl"

# EATP-034: auto-apply draft/send state per job (rove.apply.store).
# Append-only, same crash-safety discipline as TRACKING_FILE/INBOX_FILE —
# latest entry per signature wins. Separate from TRACKING_FILE: an
# "applied"/"dismissed" tracking action is Kevin's own decision, while an
# ApplicationEntry is this engine's own state machine (draft_ready ->
# submitted, or manual_required/failed) for a job it's trying to apply to.
APPLICATIONS_FILE = DATA_DIR / "applications.jsonl"

# EATP-034: Kevin's real resume, uploaded to Greenhouse/Lever's file inputs.
# Gitignored, same as `.env` — never committed. Not present until Kevin
# places it here (or the deploy step copies it to the VM); rove.apply.browser
# treats a missing file as "can't fill this required field", never a crash.
RESUME_FILE = DATA_DIR / "resume.pdf"

# Auto-apply master switch (EATP-034). Off by default — flip only after a
# manual smoke test on the real VM confirms memory stays healthy (see
# projects/EATP-034-auto-apply/CHARTER.md Definition of Done).
AUTO_APPLY_ENABLED = os.getenv("ROVE_AUTO_APPLY_ENABLED", "0") == "1"

# Match-quality harness (EATP-017, P22) — Kevin's good/bad labels on shown
# jobs (rove.eval.labels) and the precision snapshot they're
# compared against (rove.eval.report).
EVAL_DIR = DATA_DIR / "eval"
EVAL_LABELS_FILE = EVAL_DIR / "labels.jsonl"
EVAL_BASELINE_FILE = EVAL_DIR / "baseline.json"

# Orchestrator checkpoints (EATP-014) — let a crashed/interrupted run resume
# without re-scraping or re-paying for AI (CLAUDE.md golden rule 3).
CHECKPOINT_FILE = DATA_DIR / "checkpoint.json"
AI_CHECKPOINT_FILE = DATA_DIR / "ai_checkpoint.jsonl"


def raw_source_file(source: str) -> Path:
    """Path to a source's raw JSONL file (e.g. 'occ' -> data/raw/occ.jsonl)."""
    return RAW_DIR / f"{source}.jsonl"


# Versioned criteria data (EATP-002) — who Kevin is, what a good job means.
PROFILE_FILE = BASE_DIR / "profile.toml"
CRITERIA_FILE = BASE_DIR / "criteria.toml"


# ---------------------------------------------------------------------------
# Search (single source of truth; was duplicated across collectors)
# ---------------------------------------------------------------------------
# Spanish terms: searching in Spanish biases toward the local/LatAm market and
# avoids English postings that later get penalized for requiring advanced
# English (see legacy config.py for the same rationale).
SEARCH_TERMS = [
    "analista de datos",
    "analista de negocios",
    "analista de inteligencia de negocios",
    "analista bi",
    "analista power bi",
    "analista de reportes",
    "analista de informacion",
    "especialista en datos",
    "analista funcional",
    # EATP-028 (2026-08-21 backlog): widen the net without drowning it —
    # measure per source, drop a term if it's mostly noise (see ROADMAP.md).
    "analista de inteligencia comercial",
]

# English terms: for remote-first/global boards (Remotive, RemoteOK, We Work
# Remotely, Himalayas — EATP-007) that post almost exclusively in English.
# See docs/governance/SEARCH-STRATEGY.md.
ENGLISH_SEARCH_TERMS = [
    "data analyst",
    "business intelligence analyst",
    "reporting analyst",
    "business analyst",
    "bi analyst",
    "analytics analyst",
    # EATP-028 (2026-08-21 backlog): widen the net without drowning it —
    # measure per source, drop a term if it's mostly noise (see ROADMAP.md).
    "power bi developer",
    "business intelligence developer",
    "data visualization analyst",
    "insights analyst",
    "operations data analyst",
    "supply chain data analyst",
    "business systems analyst",
    "sap data analyst",
    "automation analyst",
    "people analytics",
]

# Curated ATS company boards (EATP-008) — remote-friendly companies with a
# public Greenhouse/Lever board, seeded with defaults confirmed live to have
# open postings. v1 is a hand-maintained list; automatic discovery is
# backlog. Grow freely — each entry is just a company's board slug.
ATS_COMPANIES: dict[str, list[str]] = {
    "greenhouse": [
        "gitlab",
        "stripe",
        "coinbase",
        "figma",
        "elastic",
        "asana",
        "discord",
        "webflow",
        "mixpanel",
        "amplitude",
        "vercel",
        "airtable",
        # EATP-020: added after LinkedIn dominated 74% of the final list on a
        # real run and lever/remoteok both yielded 0 — live-verified
        # (2026-08-14) each of these currently has open Data/BI/Business
        # Analyst titles on its public Greenhouse board (not just a big
        # board with unrelated roles).
        "instacart",
        "affirm",
        "brex",
        "lyft",
        "doximity",
        "chime",
        "flexport",
    ],
    # EATP-020 (2026-08-14): tried growing this list — probed ~20 well-known
    # remote-friendly companies (vanta, airbyte, linear, retool, posthog,
    # notion, plaid, zapier, docusign, ramp, snowflake, ...), all 404
    # (moved off Lever). Confirms the original docstring's finding: Lever's
    # public-board ecosystem has genuinely shrunk, this isn't a bug to fix.
    # Of the 2 already here, palantir has 300+ live postings but zero in the
    # Data/BI/Business Analyst space right now, and clari's board is empty.
    # Not worth chasing further without a new real slug to try.
    "lever": ["palantir", "clari"],
}

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
MAX_DAYS_OLD = 15

# EATP-031: Kevin's own timezone (Morelia, Michoacán) — used only to group
# inbox entries into "Hoy/Ayer/Esta semana" the way HE experiences the day,
# not the server's UTC clock. Mexico abolished DST in 2022, so this is a
# fixed UTC-6 offset year-round, not a moving target.
KEVIN_TIMEZONE = ZoneInfo("America/Mexico_City")

# How many days a content signature is considered "already seen" (ADR-001).
# Owned here; enforced by the cache in EATP-010. Kevin confirmed 30 days.
SIGNATURE_SEEN_WINDOW_DAYS = 30

# Cross-source fuzzy dedup (EATP-010, rapidfuzz 0-100 scale): two jobs at the
# same normalized company with description similarity at/above this collapse
# to one, regardless of title (SCRAPING-GOTCHAS.md #4.3 — title is never a
# required match).
DEDUP_DESCRIPTION_SIMILARITY_THRESHOLD = 90

# Source health (EATP-011, ADR-008): a source's raw yield below this fraction
# of its own rolling baseline is flagged "low". How many past runs feed that
# baseline, and the minimum runs of history needed before a baseline is
# trusted at all (too little history -> compare against nothing, not a
# misleading number).
HEALTH_LOW_YIELD_RATIO = 0.3
HEALTH_BASELINE_MAX_RUNS = 10
HEALTH_MIN_RUNS_FOR_BASELINE = 2

# ---------------------------------------------------------------------------
# AI layer (EATP-012, ADR-003) — cloud-only, multi-provider with fallback.
# ---------------------------------------------------------------------------
AI_USAGE_FILE = DATA_DIR / "ai_usage.json"

# Kevin (2026-08-12): order by QUALITY first, degrading only once a provider's
# daily quota is actually exhausted — not by raw speed. Gemini 2.5 Flash is
# the best free-tier model available but has a tiny daily cap; Groq is strong
# and fast with a generous cap; Gemini Flash-Lite is the big-quota workhorse;
# OpenRouter's free models are the last, most variable-quality resort. The
# router falls back on the real error it gets, so exact published limits
# (which drift) don't need to be exact for this to work.
AI_PROVIDER_ORDER = [
    provider.strip()
    for provider in os.getenv(
        "AI_PROVIDER_ORDER", "gemini_flash,groq,gemini_flash_lite,openrouter"
    ).split(",")
    if provider.strip()
]

GROQ_API_KEY = os.getenv("GROQ_API_KEY") or None
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or None
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or None

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# "-latest" aliases (not a pinned "2.5"): confirmed 2026-08-12 that
# "gemini-2.5-flash" 404s for new API keys ("no longer available to new
# users") even though it still lists in the API — Google had already moved
# newer generations (3.x) in by then. The aliases track whatever Google
# currently recommends, so this doesn't go stale the same way again.
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-flash-latest")
GEMINI_FLASH_LITE_MODEL = os.getenv(
    "GEMINI_FLASH_LITE_MODEL", "gemini-flash-lite-latest"
)
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)

# Jobs per AI request. Keeps prompts within per-day TOKEN caps (which bite
# before per-day request caps on the bigger models) while still batching
# enough to not burn the request-count cap either.
AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", "10"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))
AI_RETRY_BACKOFF_SECONDS = float(os.getenv("AI_RETRY_BACKOFF_SECONDS", "2.0"))
# Neither provider SDK was given an explicit timeout before (2026-08-16,
# Kevin's live report: "Cancelar" did nothing) — an AI call that just hangs
# instead of erroring blocks the run for however long the SDK's own default
# is (the OpenAI SDK's is 600s), and no amount of checking a flag *between*
# batches (pipeline.py's cooperative cancellation) can interrupt a single
# call already in flight. Bounding it here means the worst case is now this
# many seconds, not effectively unbounded — Cancelar becomes reliable within
# that bound instead of only working when a run happens to be between calls.
AI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_configured = False


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once. Quiet by default (WARNING).

    Callers (orchestrator, web server, ad-hoc scripts) call this at startup.
    Importing this module never configures logging on its own — no side
    effects on import.
    """
    global _configured
    if _configured:
        return
    resolved = (level or os.getenv("LOG_LEVEL", "WARNING")).upper()
    logging.basicConfig(level=resolved, format=_LOG_FORMAT)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
