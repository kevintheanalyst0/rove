# Rove

A personal, **remote-first job-discovery engine** for Kevin — the rebuild of
*JobMatchEngine*. It collects Data Analyst / BI / Business Analyst vacancies from
multiple sources, filters them hard for genuine remote + real fit, evaluates them with
AI, and shows the results in a clean local web UI. No terminal, no manual triage.

**North star: quality of matches, not volume.** A short list Kevin actually wants to
apply to beats a long one he has to wade through.

## Cómo correrlo (Kevin)

**La forma fácil — un acceso** (está en esta misma carpeta,
`D:\Development\Rove\`):

- **`Rove.vbs`** — abre el navegador siempre en la misma pantalla de inicio,
  con tres botones: **Iniciar búsqueda**, **Limpiar caché** y **Ver dashboard de la
  última corrida** (este último solo aparece si ya hay una corrida previa). Nunca
  arranca nada por su cuenta — vos elegís qué hacer cada vez que lo abrís.

No se abre ninguna ventana de consola (EATP-023) — el servidor corre invisible y se
apaga solo cuando cerrás la pestaña del navegador (esperá unos 20 segundos; si volvés
a abrir la página rápido, como al refrescarla, no se apaga). Si querés un acceso
directo en el Escritorio, clic derecho sobre `Rove.vbs` → *Enviar a* →
*Escritorio (crear acceso directo)*.

**La forma manual** (si el `.vbs` no te funciona, o querés ver qué está pasando):
1. Abre PowerShell o CMD en esta carpeta (`D:\Development\Rove`).
2. Levanta el servidor:
   ```bat
   .venv\Scripts\python.exe -m uvicorn rove.web.server:app --host 127.0.0.1 --port 8000
   ```
3. Abre `http://127.0.0.1:8000` en el navegador.

**Una vez adentro:**
1. Aprieta **"Iniciar búsqueda"**. Vas a ver el spinner con el estado en vivo; cuando
   termine, se muestra el dashboard con los resultados.
2. En el dashboard puedes marcar cada vacante **Apliqué** / **No me interesa** — las que
   marques "no me interesa" no vuelven a aparecer en corridas futuras.

Para apagar el servidor, simplemente cerrá la pestaña del navegador (se apaga solo a
los ~20 segundos). Si lo corriste manualmente en una terminal, `Ctrl+C` ahí también funciona.

### Corrida diaria automática (opcional, no activada)

Ver `docs/governance/AUTOMATION.md` para la receta documentada (Task Scheduler de
Windows + `wsl.exe`) por si en algún momento quieres activarla. Hoy queda apagada a
propósito — cada corrida gasta cuota gratuita de IA.

## Repo map

```
rove/
├── CLAUDE.md              ← how Claude Code operates in this repo
├── ROADMAP.md              ← the 18-project build plan + status dashboard
├── CHANGELOG.md             ← what shipped, grouped by EATP project
├── README.md                ← you are here
├── pyproject.toml           ← package + dependency definition
├── requirements.txt          ← pip mirror of dependencies
├── .env.example                ← copy to .env and fill in API keys
├── docs/
│   ├── governance/          ← authoritative design docs (one file per topic)
│   ├── adr/                 ← architecture decision records
│   └── diagnosis/           ← review of the legacy system + problem map
├── projects/
│   ├── _TEMPLATE/            ← charter + checklist templates
│   └── EATP-001 … 018/       ← one folder per project (charter + checklist)
├── src/rove/         ← the package
├── tests/                    ← tests + fixtures (real job records, trimmed)
├── data/                     ← runtime data (gitignored)
└── legacy/                   ← the original JobMatchEngine, read-only reference
```

## Design principles

- **Quality over volume.** A short list Kevin wants to apply to beats a long noisy one.
- **Remote means remote.** Hybrid/onsite jobs are rejected, not shown with a wrong flag.
- **Free, cloud-hosted AI.** Nothing runs on Kevin's machine; multi-provider with
  fallback so a tiny quota never stalls a run.
- **No terminal for the user.** The product is a web page with a working-spinner.
- **Small, safe sessions.** One project per session; crash-aware; token-disciplined.

See `docs/governance/ARCHITECTURE.md` for the full system design and `CHANGELOG.md` for
what each build session shipped.

## Development

Runs natively on Windows (EATP-025 — it used to run under WSL; see
`docs/governance/DEPENDENCIES.md` for why it moved). Python 3.12 via `uv`:

```bat
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv\Scripts\python.exe -m playwright install chromium   REM UI visual verification
.venv\Scripts\python.exe -m pytest                        REM offline, no live AI calls
```

See `CLAUDE.md` for the full operating contract this project was built under, and
`docs/governance/DEPENDENCIES.md` for what each dependency is for.
