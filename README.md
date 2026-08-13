# Career Radar

A personal, **remote-first job-discovery engine** for Kevin — the rebuild of
*JobMatchEngine*. It collects Data Analyst / BI / Business Analyst vacancies from
multiple sources, filters them hard for genuine remote + real fit, evaluates them with
AI, and shows the results in a clean local web UI. No terminal, no manual triage.

**North star: quality of matches, not volume.** A short list Kevin actually wants to
apply to beats a long one he has to wade through.

## Cómo correrlo (Kevin)

**La forma fácil — dos accesos, como en la versión vieja** (están en esta misma carpeta,
se ven desde Windows en
`\\wsl.localhost\Ubuntu-24.04\home\kevin\Projects\career-radar\`):

- **`Career Radar - Ejecutar busqueda.bat`** — arranca una corrida completa (recolecta,
  filtra, evalúa con IA) y abre el navegador mostrando el progreso en vivo.
- **`Career Radar - Ver resultados.bat`** — solo abre el dashboard con los resultados de
  la última corrida, sin arrancar nada nuevo.

En ambos casos se abre una ventana negra; para apagar el servidor, cerrala (o Ctrl+C
adentro). Si querés accesos directos en el Escritorio, clic derecho sobre cada `.bat` →
*Enviar a* → *Escritorio (crear acceso directo)*.

**La forma manual** (si el `.bat` no te funciona, o querés ver qué está pasando):
1. Abre una terminal de Ubuntu/WSL en esta carpeta.
2. Activa el entorno y levanta el servidor:
   ```bash
   source .venv/bin/activate
   uvicorn career_radar.web.server:app --host 127.0.0.1 --port 8000
   ```
3. Abre `http://127.0.0.1:8000` en el navegador.

**Una vez adentro:**
1. Aprieta **"Iniciar búsqueda"**. Vas a ver el spinner con el estado en vivo; cuando
   termine, se muestra el dashboard con los resultados.
2. Si LinkedIn o Indeed piden verificación humana durante la corrida, va a aparecer una
   ventana de Chrome pidiéndotelo, ahora siempre maximizada — resuélvela ahí (el sistema
   espera hasta 5 minutos; si no llegas a tiempo, esa fuente se omite y el resto de la
   corrida sigue igual). Si la ventana de Chrome no aparece en pantalla, probá reiniciar
   Ubuntu/WSL (`wsl --shutdown` desde PowerShell y volver a abrir la terminal) — es un
   problema conocido de WSLg, no del sistema.
3. En el dashboard puedes marcar cada vacante **Apliqué** / **No me interesa** — las que
   marques "no me interesa" no vuelven a aparecer en corridas futuras.

Para cerrar el servidor, `Ctrl+C` en la terminal.

### Corrida diaria automática (opcional, no activada)

Ver `docs/governance/AUTOMATION.md` para la receta documentada (Task Scheduler de
Windows + `wsl.exe`) por si en algún momento quieres activarla. Hoy queda apagada a
propósito — cada corrida gasta cuota gratuita de IA, y una corrida automática sin
supervisión no puede resolver un captcha de LinkedIn/Indeed si aparece.

## Repo map

```
career-radar/
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
├── src/career_radar/         ← the package
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

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium   # browser-driven collectors + UI visual checks
pytest                          # runs offline against fixtures — no live AI calls
```

See `CLAUDE.md` for the full operating contract this project was built under, and
`docs/governance/DEPENDENCIES.md` for what each dependency is for.
