# Rove

A personal, **remote-first job-discovery engine** for Kevin — the rebuild of
*JobMatchEngine*. It collects Data Analyst / BI / Business Analyst vacancies from
multiple sources, filters them hard for genuine remote + real fit, evaluates them with
AI, and shows the results in a clean local web UI. No terminal, no manual triage.

**North star: quality of matches, not volume.** A short list Kevin actually wants to
apply to beats a long one he has to wade through.

## Cómo correrlo (Kevin)

**Desde EATP-032 (2026-08-27), Rove ya no se abre localmente — corre 24/7 en un
servidor propio** (Oracle Cloud, siempre encendido), y se accede desde cualquier
dispositivo conectado a Tailscale — iPhone o PC, es el mismo servidor, los mismos
datos, sin nada que sincronizar entre ellos:

```
http://100.97.143.79:8000
```

(o el nombre `rove-vm.tail6049ca.ts.net:8000`, equivalente). El único requisito es
tener Tailscale conectado en ese dispositivo — sin eso, la app se ve "no disponible"
aunque el servidor esté sano.

El viejo launcher de escritorio (`Rove.vbs` + `scripts/run_web.{bat,sh}`) se retiró
del repo (2026-09-01) — dejó de tener sentido una vez que correr Rove localmente en
la laptop de Kevin ya no es el flujo real. Ver `deploy/README.md` para el detalle del
servidor y `docs/adr/` para por qué se hizo el cambio (EATP-032).

**Una vez adentro:**
1. Aprieta **"Iniciar búsqueda"** para forzar una corrida nueva fuera del horario
   automático (7am hora de Kevin, todos los días, sola). Vas a ver el spinner con el
   estado en vivo; cuando termine, se muestra el dashboard con los resultados.
2. En el dashboard puedes marcar cada vacante **Apliqué** / **No me interesa** — las que
   marques "no me interesa" no vuelven a aparecer en corridas futuras.
3. Para vacantes de Greenhouse/Lever, el motor de auto-apply (EATP-034/035) puede
   dejar un borrador de aplicación listo para revisar y enviar — ver el badge
   "Aplicación lista" en la tarjeta.

### Corrida diaria automática

Ya está activa — no es opcional ni algo por configurar. Un `systemd` timer
(`rove-daily-run.timer`) en el servidor dispara la corrida todos los días a las 7am
hora de Kevin. Ver `deploy/README.md` para el detalle completo; `docs/governance/
AUTOMATION.md` documenta el plan original (pre-VM), superseded por esto.

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
