# EATP-016 — Web UI — results dashboard + job tracking — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Dashboard
- [x] job cards + grade pills + remote badge
- [x] filters + apply
- [x] self-hosted fonts/assets (reuses EATP-015's vendored Inter, no new assets needed)

### Phase 2 — Tracking
- [x] applied/dismissed endpoints + store
- [x] NEW badge from history
- [x] hide-dismissed default

### Phase 3 — Close
- [x] dashboard + tracking tests
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 20:33 | start |  | Sesión iniciada tras confirmación de Kevin ("sigue, con el default") |
| 2026-08-12 20:33–20:46 | Fases 1-3 | ~13 min | Backend, dashboard+tracking, verificación visual con Playwright (estático y en vivo), tests, cierre |
| 2026-08-12 20:46–22:12 | Rediseño v2 -> v3 | ~86 min | Kevin probó la app en vivo y pidió rehacer la identidad visual por completo — ver notas |

**Total project time:** ~99 min

## Session notes
- Backend: `GET /results` (last `RunResult` + Kevin's applied/dismissed status per job,
  merged fresh on every call) and `POST /track` (records to new `tracking/store.py`,
  mirrors `history/store.py`'s append-only-latest-wins shape). Dismissed signatures feed
  back into `quality/filters.gate()` via a new `dismissed` param, wired in `pipeline.py`.
- `RunResult` gained `new_signatures` — computed in `pipeline._persist()` via
  `history_store.mark_new()` **before** `record_run()` (ordering matters: after
  `record_run()`, every job in this run would already count as "known"). Tracking status,
  by contrast, has no such ordering hazard, so it's resolved live at request time instead
  of frozen into `RunResult`.
- Frontend: `results` is one more state in EATP-015's same SPA state machine, not a
  second page — `done` holds on the checkmark ~1.1s then cross-fades into the dashboard
  (`transitionToState()`), exactly the transition Kevin asked for while planning
  EATP-015. Job cards, grade pills, filters (grade/source/remote-only/search/hide-
  dismissed), NEW badge, pros/contras expander, and the two tracking actions all client-
  rendered from `/results` — no new backend routes needed per filter.
- Verified visually with Playwright against a real running server, not just pytest:
  static dashboard render + filters + dismiss/reveal + persistence across reload, AND
  the full live flow (idle → click Iniciar → working → done → fade → results) with
  zero console errors. `main.wide` widens the glass panel only for the results state.
- 305/305 tests pass repo-wide (11 new); `ruff check` clean on every changed file.

### Rediseño visual v2 -> v3 (mismo día, tras probar en vivo)
Kevin probó la v2 (vidrio azul oscuro) con datos reales y la comparó directamente contra
capturas del sistema legacy: sin identidad (sin logo, sin sidebar), sin poder ver el
detalle de una vacante (pros/contras/resumen de IA) sin salir a LinkedIn/OCC, tarjetas de
tamaño inconsistente, y el `<select>` nativo de los filtros era ilegible sobre el vidrio
oscuro (bug real, no solo gusto). Iteró la dirección visual con 5 vistas previas
(Artifact) antes de tocar código real — violeta vs. azul "Aero" -> identidad + sidebar +
modal de detalle -> corrección de bugs (blur invisible, hover no se notaba, sin
logos) -> luego un giro completo a un tema **claro** "Apple + Aero" a partir de una
imagen de referencia + spec escrito suyo -> tres rondas de afinado (intensidad del
glass, logos reales, caja de resumen de IA "arcoíris") -> balance final del glass.
Solo se construyó de verdad hasta que confirmó cada paso.

**Lo que cambió de verdad (`web/static/{css,js}` reescritos, `web/static/icons/` nuevo):**
- Paleta clara (`#F5F6F8` base) con 5 blobs pastel muy grandes y casi estáticos
  (`filter: blur()` + `@keyframes drift` lentísimo) en vez del azul oscuro animado.
- Sidebar real: logo (SVG "radar" inline), Estado, Resumen (número grande + 5 barras:
  Excelentes/Buenas/Regulares/Bajas/Evaluadas — mapeo propio: A+=Excelentes, A=Buenas,
  B=Regulares, C+D=Bajas, Evaluadas=`counts.ai_evaluated`, no es un grado), Fuentes con
  ícono por plataforma, y "Buscar de nuevo" como tarjeta pequeña en vez de botón grande.
- Modal de detalle por vacante (clic en la tarjeta o "Ver detalles"): 3 tarjetas de
  puntaje (final/filtro/IA — mapea 1:1 a `final_score`/`prefilter_score`/`ai_score`),
  caja de resumen de IA (un solo tono lavanda, no degradado), pros/contras con
  check/X, y ahí viven "Apliqué"/"No me interesa" (ya no en la tarjeta, para que todas
  las tarjetas midan lo mismo sin importar cuántos pros/contras tengan).
- Dropdowns de grado/fuente reescritos como menús propios (`.dropdown-btn` +
  `.dropdown-menu`) — nunca más el `<select>` nativo.
- Logos reales de LinkedIn/Indeed/Greenhouse vendorizados en `web/static/icons/`
  (Simple Icons, CC0-1.0 — verificado antes de usar). OCC/Computrabajo/otras fuentes sin
  ícono de marca estandarizado se quedan con una inicial de color a propósito.
- Verificado con Playwright contra un servidor real en cada ronda (no solo la maqueta):
  filtros, modal, descartar/revertir, persistencia tras recargar, cero errores de
  consola — igual que el resto del proyecto.
- `pytest` no se tocó (backend sin cambios en esta parte): 305/305 siguen verdes.

**Bug real encontrado por Kevin tras el commit anterior:** nunca se implementaron los
breakpoints responsivos de su especificación (§25) — en una ventana angosta, la sidebar
de ancho fijo (272px) + el grid que no encoge por debajo de `minmax(270px, 1fr)` sumaban
más ancho del que cabía; `overflow-x: hidden` en `body` lo ocultaba en vez de arreglarlo,
así que se veía como tarjetas "saliéndose" de la sidebar. Agregados 3 breakpoints
(1099px: sidebar más angosta + grid 2 columnas; 759px: sidebar pasa a sección superior de
ancho completo, grid 1 columna; 480px: paddings más chicos). Verificado con Playwright en
1500/1024/820/390px contra el servidor real con los datos reales de Kevin (mismos números
que en su captura: Bajas 62, Evaluadas 47) — cero desbordamiento horizontal en ningún
tamaño.
