# EATP-004 — HTTP collectors — OCC & Computrabajo (refactor) — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 0 — Job model: thin_description flag
- [x] auto-validator in models.py + DATA-CONTRACTS.md + tests

### Phase 1 — OCC
- [x] port to framework (rebuilt: no legacy import; real pagination end-detection instead of fixed 2-page cap)
- [x] description quality flag (via Job model, EATP-004 Phase 0)
- [x] fixture test

### Phase 2 — Computrabajo
- [x] port to framework (rebuilt: no legacy import; kept the real end-marker pagination technique)
- [x] description quality flag (via Job model)
- [x] fixture test (incl. a fix found along the way: `education` exclusion category was English-only — added docente/profesor/profesora/"maestro de")

### Phase 3 — Close
- [x] register both
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Fases 0-4 (thin_description, OCC, Computrabajo, registro, cierre) | ~1 h | Rebuild deliberado, no port; ver notas |

**Total project time:** ~1 h (2026-08-12)

## Session notes
Reconstruidos (no portados) `collectors/occ.py` y `collectors/computrabajo.py` sobre el
framework de EATP-003: usan `http.py` (retry/pacing), nunca hardcodean `remote_status`
(queda `unknown`, el gate de EATP-009 decide), no filtran por antigüedad ni por inglés
dentro del colector (movido a EATP-009), y no hacen dedup difuso propio (movido a
EATP-010). Se conservó el conocimiento real del sitio: endpoints JSON de detalle,
mapeo de campos, selectores de Computrabajo, y su técnica de fin-de-resultados por
marcador HTML — que además se copió a OCC, reemplazando su tope fijo de 2 páginas por
detección real de fin de resultados. Nuevo campo `Job.thin_description` (auto-calculado
en el modelo, EATP-001) para que P21 (calidad de descripción) no dependa de que cada
colector lo implemente por su cuenta. Fix menor encontrado al probar: la categoría
`education` en `criteria.toml` solo tenía palabras en inglés; se agregaron
docente/profesor/profesora/"maestro de". Tests: fixtures reales envueltos en el
formato real de cada sitio (HTML/JSON sintético) y servidos por `httpx.MockTransport`
— sin red real. 16 tests nuevos, 88/88 en todo el proyecto, ruff limpio en `src/`/`tests/`.
