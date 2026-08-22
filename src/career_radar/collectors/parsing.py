"""Shared text/date parsing for the HTTP-based collectors.

The Spanish-language parts (OCC, Computrabajo post relative dates in the same
handful of Spanish formats) live alongside a small English-market helper used
by the remote-first boards (EATP-007), which have no server-side keyword
search and need a client-side match instead. `extract_job_posting_ld_json` and
`slug_to_text` (EATP-030) serve the sitemap/category-discovered LatAm boards
(Hireline, WeRemoto, RemotoJob), which all embed a standard schema.org
`JobPosting` block per page instead of exposing a JSON API.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

_LD_JSON_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)

_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str | None) -> str:
    """Collapse whitespace and trim."""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text).strip()


def parse_days_old_es(text: str | None) -> int:
    """Convert a Spanish relative date to an age in days.

    Covers OCC/Computrabajo's formats: "hace X horas", "ayer", "X días",
    "X semanas", "X meses", "más de 30 días", and "DD de MES". Returns 999
    when it can't be parsed (falls outside any recency filter downstream).
    """
    text = (text or "").lower().strip()
    if not text:
        return 999

    if "más de 30" in text or "mas de 30" in text:
        return 31
    if text == "ayer":
        return 1
    if "hora" in text or "minuto" in text or "hoy" in text or "recién" in text:
        return 0

    digits = "".join(c for c in text if c.isdigit())

    if "semana" in text:
        return (int(digits) if digits else 1) * 7
    if "mes" in text:
        return (int(digits) if digits else 1) * 30
    if "día" in text or "dia" in text:
        return int(digits) if digits else 0

    try:
        parts = text.split(" de ")
        day = int(parts[0].strip())
        month = _MONTHS_ES[parts[1].strip()]
        now = datetime.now(UTC)
        posted = datetime(now.year, month, day, tzinfo=UTC)
        return max((now - posted).days, 0)
    except (ValueError, KeyError, IndexError):
        return 999


def matches_any_term(text: str, terms: list[str]) -> bool:
    """Case-insensitive substring match against a list of search phrases.

    Used by boards whose API/feed ignores server-side search (RemoteOK,
    Himalayas) or only exposes a broad category (We Work Remotely) — the
    collector fetches once and filters client-side instead.
    """
    lowered = text.lower()
    return any(term in lowered for term in terms)


def slug_to_text(slug: str) -> str:
    """A URL slug ("responsable-de-plataforma-sap") to space-separated text,
    for matching against `matches_any_term`'s space-separated search phrases
    (EATP-030: Hireline/RemotoJob discover candidate postings via a sitemap of
    URLs, with no title text available until the detail page is fetched — the
    slug itself is the only cheap, pre-fetch signal to prefilter on)."""
    return slug.replace("-", " ").replace("_", " ")


def extract_job_posting_ld_json(html: str) -> dict | None:
    """Find and parse the schema.org `JobPosting` JSON-LD block embedded in a
    job-posting page (EATP-030: Hireline, WeRemoto, and RemotoJob all embed
    one, since it's a standard SEO practice — field names are consistent
    across sites even though each page also carries other, unrelated
    `<script type="application/ld+json">` blocks (WebSite, Organization, ...),
    and at least one site (RemotoJob) emits a raw, unescaped newline inside a
    string value that breaks strict JSON — `strict=False` tolerates it the
    same way Python's own `json` module is designed to.

    Returns `None` if no block parses to a `JobPosting` (either a bare object
    or one entry in an array of `@graph`-style objects).
    """
    for match in _LD_JSON_RE.finditer(html):
        try:
            data = json.loads(match.group(1), strict=False)
        except ValueError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
                return candidate
    return None
