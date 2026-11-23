"""Which inbox vacancies the nightly runner should try, in what order (EATP-037).

Rules come from Kevin: only sources whose application flow works in his real
Chrome (OCC, Computrabajo), nothing in the categories he excluded, nothing from
companies that mass-post (his "traps to harvest data" rule), nothing already
sitting on his skipped list, and no grade-D matches (they would burn quota on
roles that do not fit). Vacancies whose pending question he has since answered
go first.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SUPPORTED_SOURCES = frozenset({"occ", "computrabajo"})
GRADE_RANK = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4}
MIN_GRADE = "C"
MASS_POSTER_THRESHOLD = 5

EXCLUDED_TITLE = re.compile(
    r"call ?center|customer (support|service)|atenci[oó]n (a|al) clientes?|soporte|"
    r"ventas|vendedor|sales|marketing|mercadotecnia|contab|n[oó]mina|payroll|"
    r"recursos humanos|reclutad|\bhr\b|telemarket|asesor(a)? comercial",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    signature: str
    url: str
    title: str
    company: str
    source: str
    grade: str
    score: int
    days_old: int | None


def clean_url(url: str) -> str:
    """Drop what only tracked Rove's search session: the fragment everywhere, and OCC's
    query string (rank, sessionid, uuid...). The posting itself is the path."""
    parts = urlsplit(url)
    query = "" if parts.netloc.endswith("occ.com.mx") else parts.query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _company_key(company: str) -> str:
    return re.sub(r"\s+", " ", (company or "").strip().casefold())


def candidates_from_inbox(
    inbox: dict[str, Any],
    *,
    sources: frozenset[str] = SUPPORTED_SOURCES,
    min_grade: str = MIN_GRADE,
    mass_threshold: int = MASS_POSTER_THRESHOLD,
    exclude_urls: frozenset[str] | set[str] = frozenset(),
    retry_urls: list[str] | tuple[str, ...] = (),
) -> list[Candidate]:
    """Eligible vacancies, best first (retries, then score, then freshest)."""
    items = [item for bucket in inbox.get("buckets", {}).values() for item in bucket]
    per_company = Counter(_company_key(item["scored"]["job"].get("company", "")) for item in items)
    limit = GRADE_RANK[min_grade]
    retry_rank = {url: index for index, url in enumerate(retry_urls)}

    picked: list[Candidate] = []
    seen_urls: set[str] = set()
    for item in items:
        scored = item["scored"]
        job = scored["job"]
        url = clean_url(job.get("url") or "")
        if job.get("source") not in sources or not url or url in exclude_urls or url in seen_urls:
            continue
        if EXCLUDED_TITLE.search(job.get("title", "")):
            continue
        if GRADE_RANK.get(scored.get("grade"), 99) > limit:
            continue
        company = _company_key(job.get("company", ""))
        if company and per_company[company] >= mass_threshold:
            continue
        seen_urls.add(url)
        picked.append(
            Candidate(
                signature=item["signature"],
                url=url,
                title=job.get("title", ""),
                company=job.get("company", ""),
                source=job.get("source", ""),
                grade=scored.get("grade", ""),
                score=int(scored.get("final_score", 0)),
                days_old=job.get("days_old"),
            )
        )

    def order(candidate: Candidate) -> tuple[int, int, int]:
        is_retry = 0 if candidate.url in retry_rank else 1
        return (is_retry, -candidate.score, candidate.days_old if candidate.days_old is not None else 999)

    return sorted(picked, key=order)
