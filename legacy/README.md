# legacy/ — the original JobMatchEngine (read-only reference)

This is Kevin's current, working system. **Do not run it or modify it.** It's here so
you (Claude Code) can reuse hard-won, site-specific knowledge while rebuilding —
especially:

- `jobmatch/collectors/occ.py`, `computrabajo.py` — the JSON endpoints and card
  selectors for those sites (fast HTTP, no browser).
- `jobmatch/collectors/linkedin.py` + `linkedin_api.py` — how it lists job ids with a
  browser and fetches details via LinkedIn's guest API.
- `jobmatch/collectors/indeed.py` — Indeed's JSON-LD parsing and captcha points.
- `jobmatch/collectors/filters.py` — the exclusion/English lists to port and expand.
- `jobmatch/pipeline/prompts.py` — the AI evaluation prompt to adapt (then fix its
  looseness per the rubric).
- `jobmatch/pipeline/{process,state,ai}.py` — resumable batches, quota pause, retries.
- `app.py`, `assets/style.css` — the existing dark/violet look for reference.

**Reuse the knowledge, not the structure.** The rebuild lives in `src/rove/`
following the charters; it does not import from `legacy/`.
