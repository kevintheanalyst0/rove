# Career Radar

A personal, **remote-first job-discovery engine** — the rebuild of *JobMatchEngine*.
It collects Data Analyst / BI / Business Analyst vacancies from multiple sources,
filters them hard for genuine remote + real fit, evaluates them with AI, and shows the
results in a clean local web UI.

> **This repository is a scaffold.** The working system is built here inside Ubuntu/WSL
> by Claude Code, **one project at a time**, following `ROADMAP.md`. When all projects
> are done, the repo is published to GitHub (EATP-018).

## Empezar (Kevin)

En una terminal de Ubuntu, dentro de esta carpeta, abre Claude Code y escribe:

```
Trabajemos en EATP-001
```

Claude hará el resto. Ver `ROADMAP.md` → "Cómo usar este repo".

## Repo map

```
career-radar/
├── CLAUDE.md              ← how Claude Code must operate (read this first)
├── ROADMAP.md             ← the 10-project plan + status dashboard
├── README.md              ← you are here
├── pyproject.toml         ← package + dependency definition
├── requirements.txt       ← pip mirror of dependencies
├── .env.example           ← copy to .env and fill in API keys
├── docs/
│   ├── governance/        ← authoritative design docs (one file per topic)
│   ├── adr/               ← architecture decision records
│   └── diagnosis/         ← review of the legacy system + problem map
├── projects/
│   ├── _TEMPLATE/         ← charter + checklist templates
│   └── EATP-001 … 018/    ← one folder per project (charter + checklist)
├── src/career_radar/      ← the package (built by Claude Code)
├── tests/                 ← tests + fixtures (real job records, trimmed)
├── data/                  ← runtime data (gitignored)
└── legacy/                ← the original JobMatchEngine, read-only reference
```

## Design principles

- **Quality over volume.** A short list Kevin wants to apply to beats a long noisy one.
- **Remote means remote.** Hybrid/onsite jobs are rejected, not shown with a wrong flag.
- **Free, cloud-hosted AI.** Nothing runs on Kevin's machine; multi-provider with
  fallback so a tiny quota never stalls a run.
- **No terminal for the user.** The product is a web page with a working-spinner.
- **Small, safe sessions.** One project per session; crash-aware; token-disciplined.

See `docs/governance/ARCHITECTURE.md` for the full picture.
