# Dependencies — master list & protocol

The authoritative dependency list is `pyproject.toml`. This file explains **what each
dependency is for**, **when it's needed**, and the **install/verify protocol** Claude
Code must follow.

## Runtime environment (EATP-025, 2026-08-18)

**The project runs natively on Windows, at `D:\Development\Career Radar`.** It was
built under WSL through EATP-024; the WSL copy at
`/home/kevin/Projects/career-radar` is kept only as a backup and is no longer the
one that runs.

Why it moved: every browser-layer failure of EATP-023/024/025 traced to WSLg's
virtualized GPU and forwarded display — a window that wouldn't repaint until
clicked, GPU context loss mid-session, and finally Chrome dying outright three runs
in a row, which hung the whole pipeline. **Legacy `jobmatch` never hit any of it,
because legacy also ran natively on Windows.** That comparison is only valid across
the same platform — see CLAUDE.md golden rule 12.

- **Python 3.12** via `uv` (`uv python install 3.12`). Windows' own Python is 3.14,
  too new to trust for the compiled dependencies here (`lxml`, `orjson`,
  `pydantic-core`); `uv` keeps 3.12 alongside it without touching the system install.
- **`uv`** lives at `C:\Users\kevin\.local\bin\uv.exe` (not on PATH by default).
- **Chromium** comes from `playwright install chromium`, which on Windows lands in
  `%LOCALAPPDATA%\ms-playwright\chromium-*\chrome-win64\chrome.exe` — note
  `chrome-win64`, not the WSL layout's `chrome-linux64`. `browser.py` resolves both.

## Protocol (every session)

1. At project start, check what's already installed **before** installing anything:
   ```bat
   .venv\Scripts\python.exe -c "import <pkg>; print('<pkg> ok')"
   uv pip show <pkg>
   ```
2. Install only what the current project needs (see "Needed by" column).
3. If a project needs a dependency **not** in this list → **ask Kevin first**
   (CLAUDE.md §8), then add it here and to `pyproject.toml` + `requirements.txt`.
4. First-time full install:
   ```bat
   uv venv --python 3.12
   uv pip install -e ".[dev]"
   REM For browser + verification projects only:
   REM   .venv\Scripts\python.exe -m playwright install chromium
   ```
5. Prefer the venv. Never install globally.

## The list

| Package | Purpose | Needed by |
|---------|---------|-----------|
| `python-dotenv` | Load `.env` (API keys, paths) | 001+ |
| `pydantic` | Typed data contracts (`Job`, `ScoredJob`, `RunResult`) with validation | 001+ |
| `httpx` | HTTP client for HTTP/JSON collectors and AI REST calls | 001, 004, 005, 006 |
| `beautifulsoup4` | Parse HTML from HTTP-based collectors | 004, 005 |
| `lxml` | Fast parser backend for BeautifulSoup | 004, 005 |
| `tenacity` | Declarative retry/backoff (network + AI) | 004, 006 |
| `python-dateutil` | Robust date parsing (posting ages, mixed formats) | 003, 004 |
| `rapidfuzz` | Fast fuzzy matching for dedup + content signatures | 003 |
| `orjson` | Fast JSON for large files; streaming-friendly | 001+ |
| `DrissionPage` | Chromium automation for LinkedIn/Indeed listing pages | 004 |
| `groq` | **Primary** AI provider (free, fast, OpenAI-compatible) | 006 |
| `google-genai` | Gemini provider (Flash-Lite / Flash) | 006 |
| `openai` | OpenAI-compatible client (OpenRouter; also works for Groq) | 006 |
| `fastapi` | Web UI backend | 009 |
| `uvicorn[standard]` | ASGI server to run FastAPI | 009 |
| `playwright` | Visual verification of the web UI | 010 |
| `pytest` (dev) | Test runner | 001+ |
| `pytest-asyncio` (dev) | Async tests (AI layer, FastAPI) | 006, 009 |
| `ruff` (dev) | Lint/format | 001+ |

## Notes & gotchas

- **`DrissionPage` needs a real Chromium.** Inside WSL, Claude Code must ensure a
  Chromium/Chrome binary is available and reachable, or run browser collectors against
  the Windows Chrome. Resolve this in EATP-003; don't block earlier projects on it.
- **`playwright` needs a browser download** (`playwright install chromium`). Originally
  planned for EATP-018/015-016 only, but EATP-003 downloaded it early: WSL has no
  trustworthy system Chromium (Ubuntu 24.04's `chromium` is snap-only and its sandboxing
  fights DrissionPage's custom profile dirs), so `collectors/browser.py` resolves to this
  same standalone binary for the browser-driven collectors (LinkedIn/Indeed). No new
  dependency — `playwright` was already in the list; this just fetches its browser asset
  sooner.
- **AI SDKs:** you don't need all three. Groq alone (via `groq` or the OpenAI-compatible
  `openai` client) covers the primary path. `google-genai` is for the Gemini fallback.
- **We drop `requests` in favor of `httpx`** and **`difflib` in favor of `rapidfuzz`**
  for speed and cleaner async. The legacy code uses the old ones — refactor as you port.
- **`langdetect`, `python-docx`, `pywin32`** from the legacy `requirements` are **not**
  in the core list — they belonged to CV tailoring (backlog).
