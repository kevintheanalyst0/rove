# EATP-005 — LinkedIn collector (refactor + harden) — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Listing
- [x] browser id listing (rebuilt: single sequential tab, not legacy's 4 parallel tabs)
- [x] 429 backoff (health-check -> event + stop this term, no crash)
- [x] event-based login (no input()) — bounded poll/wait, never blocks the terminal

### Phase 2 — Details
- [x] guest API detail fetch (rebuilt on http.py; tenacity retry replaces legacy's manual RATE_LIMIT dance)
- [x] polite concurrency (ThreadPoolExecutor, 3 workers, jittered pause per request)

### Phase 3 — Close
- [x] fixture tests
- [x] register (satisfies Collector protocol; verified live, see notes)
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Fases 1-3 + verificación en vivo | ~2.5 h | Incluye diagnóstico y fix del perfil de navegador sin sesión |

**Total project time:** ~2.5 h (2026-08-12)

## Session notes
Reconstruido (no portado) sobre el framework: navegador secuencial de una sola pestaña
por término (legacy usaba 4 en paralelo con coordinación de pausa entre hilos — más
riesgo de cuenta y complejidad para una fuente que la propia estrategia ya marca como
secundaria). Se conservó la detección de tarjetas "recomendadas", el chequeo de salud
de página y los filtros de búsqueda (remoto/24h/tiempo completo) como funciones puras,
testeables sin navegador real. Login/checkpoint se resuelve con espera acotada +
sondeo, nunca `input()`. El detalle vía API guest se reconstruyó sobre `http.py`: el
retry de tenacity ya reemplaza el manejo manual de rate-limit de legacy.

**Verificación en vivo (autorizada por Kevin):** la primera corrida real dio 0
resultados — diagnostiqué que el perfil de navegador que configuré en EATP-003
(`data/browser_profile`) era nuevo y vacío, así que LinkedIn servía la vista pública
sin login (markup distinto, sin `data-occludable-job-id`, sin poder respetar el filtro
de ubicación). Abrí una ventana visible (WSLg) para que Kevin iniciara sesión una vez
en ese perfil dedicado; tras eso, la corrida real trajo 9 vacantes genuinas con
descripciones completas. Los selectores ya construidos coincidían con el markup
autenticado real — el problema era enteramente la falta de sesión, no el código.
Cualquier proyecto futuro que dependa de un navegador con perfil persistente debe
saber que ese perfil empieza vacío y necesita este login manual de una sola vez.
