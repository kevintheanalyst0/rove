# EATP-003 — Collector framework & shared plumbing — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Contract & registry
- [x] base.py protocol+registry
- [x] result/health envelope

### Phase 2 — HTTP layer
- [x] http.py session/pacing/retry
- [x] tests

### Phase 3 — Browser base
- [x] browser.py stealth + WSL path
- [x] event-based manual-intervention (no input())
- [x] tests

### Phase 4 — Close
- [x] full pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Fase 1 + 2 (base.py, http.py, tests) | ~25 min | Incluye instalar Chromium standalone vía Playwright (sin sudo) |
| 2026-08-12 | Fase 3 + 4 (browser.py, smoke test real, cierre) | ~15 min | Smoke test headless real confirmó el path de Chromium end-to-end |

**Total project time:** ~40 min (2026-08-12)

## Session notes
Construidos `collectors/base.py` (protocolo `Collector` + `CollectorRegistry` con
enable/disable + envelope `CollectorResult` con yield count/salud), `collectors/http.py`
(sesión httpx + pacing aleatorio + retry con backoff en 429/5xx vía tenacity), y
`collectors/browser.py` (Chromium stealth con viewport aleatorio, perfil persistente
opcional, y `request_manual_intervention()` que publica al event bus en vez de
`input()`/beep). Decisión clave: en WSL no hay Chromium de sistema confiable (Ubuntu
24.04 solo lo da via snap, que sandboxea rutas custom); se resolvió instalando el
Chromium standalone que trae Playwright (`playwright install chromium`, sin sudo) y
apuntando `browser.py` ahí por defecto, con override opcional por `config.py`. Se
verificó con un arranque headless real (no solo mockeado) que el navegador lanza y
cierra limpio. 19 tests nuevos en `test_collector_framework.py`, 73/73 en todo el
proyecto, ruff limpio. Los colectores de sitio real (004-008) ya tienen su contrato
listo para implementarse encima de esta capa.
