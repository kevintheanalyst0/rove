# Architecture — Rove (target)

The target system, top to bottom. Each layer maps to one or more EATP projects. This is
the "what we're building toward"; charters own the "how, this session".

## Layered view

```
┌─────────────────────────────────────────────────────────────────────┐
│  WEB UI  (EATP-015 · 016)                                                   │
│  FastAPI backend + single-page frontend.                             │
│  "Run" button → dots spinner + live status text → results dashboard. │
│  Dark theme, violet #6D3BF5, Inter.  No terminal for the user.       │
└───────────────▲─────────────────────────────────────────────────────┘
                │ progress events + results.json
┌───────────────┴─────────────────────────────────────────────────────┐
│  ORCHESTRATOR  (EATP-014)                                            │
│  Runs the pipeline end-to-end. Resumable, crash/OOM-safe, streams &  │
│  checkpoints. Emits progress events the UI subscribes to. Speed vs   │
│  exhaustiveness knobs.                                               │
└───────▲───────────────────────▲────────────────────────▲────────────┘
        │                        │                        │
┌───────┴────────┐   ┌───────────┴──────────┐   ┌─────────┴───────────┐
│  COLLECTORS    │   │  FILTER / DEDUP /    │   │  SCORING PIPELINE   │
│  (003-008)     │──▶│  CACHE  (009-010)    │──▶│  (013)              │
│  base contract │   │  remote hard-gate    │   │  matcher pre-filter │
│  + N sources   │   │  content-sig cache   │   │  → AI deep-eval     │
│                │   │  quality gates       │   │  → validated result │
└────────────────┘   └──────────────────────┘   └─────────▲───────────┘
                                                           │ uses
                                          ┌────────────────┴────────────┐
                                          │  AI LAYER  (012)             │
                                          │  multi-provider + fallback   │
                                          │  Groq / Gemini Flash-Lite /… │
                                          │  structured output + repair  │
                                          └──────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│  FOUNDATION  (001)  config · data models (pydantic) · storage        │
│                     (atomic, streaming) · logging/event bus          │
│  CRITERIA    (002)  candidate profile · hard filters · fit rubric    │
└─────────────────────────────────────────────────────────────────────┘
```

## Package layout (target, built by Claude Code)

```
src/rove/
├── __init__.py
├── config.py                # single source of truth (env + constants)          [001]
├── models.py                # Job, ScoredJob, RunResult (pydantic)               [001]
├── storage.py               # atomic + streaming JSON/JSONL read/write           [001]
├── events.py                # progress event bus (UI subscribes)                 [001]
├── profile.py               # candidate profile loader (profile.yaml)            [002]
├── criteria.py              # hard filters + fit rubric                          [002]
├── quality/
│   ├── filters.py           # remote hard-gate, title/english/junk gates         [009]
│   ├── dedup.py             # fuzzy dedup (rapidfuzz)                             [010]
│   └── cache.py             # content-signature cache + run history              [010]
├── collectors/
│   ├── base.py              # Collector protocol + registry                      [003]
│   ├── http.py              # shared httpx session + pacing                      [003]
│   ├── occ.py computrabajo.py   (refactored; linkedin removed EATP-027,
│   │                              indeed removed EATP-033)              [004-006]
│   ├── remotive.py wwr.py remoteok.py greenhouse.py lever.py ...   (new)         [007-008]
│   └── hireline.py weremoto.py remotojob.py   (sitemap/category + JSON-LD)  [030]
├── ai/
│   ├── base.py              # Provider protocol                                  [012]
│   ├── providers/           # groq.py, gemini.py, openrouter.py, ...             [012]
│   ├── router.py            # preference order + fallback + quota tracking       [012]
│   └── parse.py             # structured-output enforce + repair                 [012]
├── scoring/
│   ├── prefilter.py         # matcher-as-gate (cheap reject + cap)               [013]
│   ├── evaluate.py          # AI deep-eval orchestration                         [013]
│   └── validate.py          # post-validation guards                            [013]
├── pipeline.py              # the orchestrator                                   [014]
└── web/
    ├── server.py            # FastAPI app                                        [015-016]
    └── static/              # single-page frontend (spinner + dashboard)         [015-016]
```

## Data flow (one run)

1. **Collect.** Each enabled collector yields normalized `Job`s. Browser sources pace
   gently; HTTP/JSON sources go fast.
2. **Gate.** Each `Job` passes the quality layer: title/english/junk gates → **remote
   hard-gate** → fuzzy dedup within the run → **content-signature cache** check (skip if
   seen recently). Survivors continue.
3. **Pre-filter.** The matcher scores survivors and **rejects** clearly-bad ones, then
   caps the count sent to AI (protects quota, focuses on plausible matches).
4. **Evaluate.** The AI layer scores each remaining job with the fixed rubric, returns
   validated structured results (score, fit, pros, contras, summary). Malformed items
   are repaired or dropped; contradictions are stripped.
5. **Rank & persist.** Results are ranked, written atomically to `data/results.json`,
   and the content-signature cache is updated.
6. **Show.** The web UI reads `results.json` and renders the dashboard; during the run
   it shows the spinner + live phase text from the event bus.

## Cross-cutting invariants

- **Remote is a hard gate, never a soft flag** (ADR-002).
- **Cache keys are content signatures, never volatile site ids** (ADR-001).
- **AI is cloud-only, multi-provider, quota-aware** (ADR-003); tests never call it live.
- **Every heavy stage streams + checkpoints**; the orchestrator can resume (CLAUDE.md §3).
- **The user never sees a terminal** (ADR-004).
