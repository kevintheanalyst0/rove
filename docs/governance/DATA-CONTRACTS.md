# Data Contracts

One shape for a vacancy, one shape for a scored vacancy, one shape for a run result.
Implemented as pydantic models in `src/career_radar/models.py` (EATP-001). Collectors,
filters, cache, scoring, and the UI all speak these — no ad-hoc dicts.

## `Job` — a normalized vacancy (collector output)

| field | type | notes |
|-------|------|-------|
| `source` | str | collector id: `occ`, `indeed`, `greenhouse`, … |
| `source_job_id` | str | the site's own id (volatile — **never** a cache key) |
| `signature` | str | **content signature** (see below); the stable identity |
| `title` | str | normalized title |
| `company` | str | normalized company; `"Unknown"` if absent |
| `description` | str | plain-text description |
| `url` | str | canonical apply/view URL |
| `remote_status` | enum | `remote` \| `hybrid` \| `onsite` \| `unknown` (see ADR-002) |
| `remote_evidence` | list[str] | phrases that drove the remote decision (auditable) |
| `posted_at` | date \| None | best-effort posting date |
| `days_old` | int | 999 if unknown |
| `location_raw` | str | as scraped, for the UI |
| `english_requirement` | enum | `compatible` \| `indeterminate` \| `reject` (EATP-028) — `reject` is explicit C1/C2/native/bilingual (hard-gated); `indeterminate` is ambiguous phrasing ("English required", "fluent") that never specifies a level, kept visible with a `confirm_english` flag instead of dropped |
| `english_evidence` | list[str] | phrase(s) that drove the `english_requirement` classification (auditable, same pattern as `remote_evidence`) |
| `seniority_hint` | str | `junior` \| `mid` \| `senior` \| `unknown` (heuristic) |
| `thin_description` | bool | auto-set when `description` < 200 chars after stripping (P21); scoring may down-weight or skip, collectors never drop the job for this alone |
| `title_caution_flags` | list[str] | ADR-009: ambiguous title words with no rescue word nearby (e.g. `engineer`, `manager`); set by the quality gate (EATP-009), advisory only for the matcher (EATP-013) — **never** a reject reason at the gate |
| `collected_at` | datetime | when this run saw it |

> **`remote` is an enum, not a bool.** The legacy `remote:bool` is exactly why hybrid
> jobs leaked. A job is shown by default only if `remote_status == remote`.

### Content signature (the stable identity)

```
signature = sha1( normalize(company) + "|" + normalize(title) + "|" + normalize(description)[:400] )
normalize = lowercase, strip accents, collapse whitespace, drop punctuation,
            remove volatile tokens (dates, "hoy", req-ids, city-of-the-day)
```

This is what the cache and cross-source dedup key on, so a job reposted daily under a
new `source_job_id` is recognized as the same posting (fixes P9).

## `ScoredJob` — a `Job` after pre-filter + AI (scoring output)

| field | type | notes |
|-------|------|-------|
| `job` | Job | the original, embedded |
| `prefilter_score` | int | cheap rule score (0–100) |
| `prefilter_passed` | bool | did it survive the pre-filter gate |
| `ai_evaluated` | bool | did the AI actually score it |
| `ai_score` | int \| None | 0–100 from the AI (canonical score if present) |
| `final_score` | int | `ai_score` if evaluated else `prefilter_score` |
| `grade` | enum | derived from `final_score` by the **single** mapping below |
| `fit` | enum | `ideal` \| `strong` \| `good` \| `moderate` \| `weak` \| `poor` |
| `pros` | list[str] | Spanish, responsibilities-focused |
| `contras` | list[str] | Spanish, only real incompatibilities (may be empty) |
| `summary` | str | Spanish, one paragraph, why this score |
| `flags` | list[str] | e.g. `remote_uncertain`, `english_required` (Layer-4 demotion, `job.english_requirement == reject` scored too high), `confirm_english` (EATP-028: `job.english_requirement == indeterminate`, never demotes), `senior_heavy` |

### The single canonical score → grade mapping (used EVERYWHERE)

```
>= 90 : A+     70–79 : B
80–89 : A      55–69 : C
                      < 55 : D
```

The legacy "B with No cons" bug came from two different grade scales. There is now
**one** mapping, in `models.py`, and both the matcher and the UI use it. Empty
`contras` is legitimate for a genuinely-good job — but the grade always matches the
number, so it can never look contradictory.

## `RunResult` — the output of one full run

| field | type | notes |
|-------|------|-------|
| `started_at` / `finished_at` | datetime | |
| `status` | enum | `running` \| `success` \| `paused` \| `error` |
| `message` | str | human-readable |
| `counts` | dict | collected / gated / prefiltered / ai_evaluated / shown |
| `funnel` | dict[str, dict[str, int]] | EATP-028/P28: `{source: {rejection_reason: count}}` — the per-source breakdown of every `quality/filters.py::gate()` rejection reason (`advanced_english_required`, `not_remote:hybrid`, `stale`, `duplicate_within_run`, `cached_recently`, `dismissed_by_kevin`, `excluded_title_or_company`), so a quiet run can be told apart from a stage/source quietly filtering a lot |
| `source_health` | list[SourceHealth] | ADR-008: per-source `ok\|low\|zero\|error` + reason, from `health/check.py` (EATP-011) |
| `jobs` | list[ScoredJob] | ranked, best first |
| `ai_usage` | dict | provider → calls made (quota visibility) |

## `SourceHealth` — one source's verdict for a run (ADR-008)

| field | type | notes |
|-------|------|-------|
| `source` | str | collector id |
| `status` | enum | `ok` \| `low` \| `zero` \| `error` — classified against the source's own rolling baseline, never a global threshold |
| `yielded` | int | this run's **raw** collector yield (before the quality gate — gate attrition must never look like a broken scraper) |
| `baseline` | float \| None | average raw yield over recent past runs; `None` when there isn't enough history yet |
| `reason` | str | calm Spanish note, e.g. `"indeed no devolvió resultados - posible bloqueo"` |

## Files on disk (`data/`, all gitignored)

| file | shape | written by |
|------|-------|-----------|
| `raw/<source>.jsonl` | `Job` per line | each collector (streamed) |
| `gated.jsonl` | `Job` per line | quality layer |
| `results.json` | `RunResult` | orchestrator (atomic) |
| `cache/signatures.jsonl` | `{signature, first_seen, last_seen, final_score}` | cache |
| `history/<run-timestamp>.jsonl` | `{signature, source, title, company, shown_at}` per shown job | history store (append-only, one file per run) |
| `health/yields.jsonl` | `{run_started_at, source, yielded, status}` per source per run | health check (EATP-011, append-only, one cumulative file — raw yield, not shown count, so gate attrition never looks like a broken scraper) |
| `status.json` | run status for the UI | orchestrator |

> Use **JSONL (one record per line)** for large collections so writes stream and a
> crash never corrupts more than the last line. Reserve pretty JSON for small files
> (`results.json`, `status.json`).
