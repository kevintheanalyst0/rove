"""Cross-source fuzzy dedup — the same posting scraped from two different
sources within one run collapses to one (SCRAPING-GOTCHAS.md #4, case 2).

Deliberately NOT ported from `legacy/jobmatch/collectors/utils.py::is_duplicate`
(CLAUDE.md golden rule 12): the legacy version required **both** title
similarity >= 0.90 **and** description similarity >= 0.95 within the same
company, so a repost with a reworded title failed the title half and got
saved twice — the exact failure SCRAPING-GOTCHAS.md #4.3 calls out. Here,
company (exact, normalized) + description similarity is the whole decision;
title is never read. Uses rapidfuzz, replacing legacy's difflib.

Jobs are grouped by normalized company first — company match is required
before any fuzzy compare runs, both because two different companies are
never the same posting and because it keeps this well clear of an O(n^2)
scan over the whole run.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from rapidfuzz import fuzz

from career_radar import config
from career_radar.models import Job, normalize

_MIN_LENGTH_RATIO = 0.7


def _is_same_posting(a: Job, b: Job, description_similarity_threshold: float) -> bool:
    desc_a, desc_b = normalize(a.description), normalize(b.description)
    if not desc_a or not desc_b:
        return False

    # Cheap pre-filter: wildly different lengths can't be a near-duplicate,
    # and skipping the fuzzy compare entirely is far cheaper than running it.
    length_ratio = min(len(desc_a), len(desc_b)) / max(len(desc_a), len(desc_b))
    if length_ratio < _MIN_LENGTH_RATIO:
        return False

    return fuzz.ratio(desc_a, desc_b) >= description_similarity_threshold


def dedup(
    jobs: Iterable[Job],
    description_similarity_threshold: float = config.DEDUP_DESCRIPTION_SIMILARITY_THRESHOLD,
) -> tuple[list[Job], list[Job]]:
    """Splits `jobs` into `(kept, dropped)`. For each company group, the
    first occurrence of a posting wins; later near-duplicates are dropped.
    """
    kept: list[Job] = []
    dropped: list[Job] = []
    by_company: dict[str, list[Job]] = defaultdict(list)

    for job in jobs:
        group = by_company[normalize(job.company)]
        match = next(
            (existing for existing in group if _is_same_posting(job, existing, description_similarity_threshold)),
            None,
        )
        if match is not None:
            dropped.append(job)
        else:
            group.append(job)
            kept.append(job)

    return kept, dropped
