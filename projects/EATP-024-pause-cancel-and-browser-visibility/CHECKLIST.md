# EATP-024 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Diagnose & fix Pausar; add Cancelar
- [x] Reproduce/diagnose why "Pausar" appears to do nothing in Kevin's real browser
- [x] Fix the actual root cause (frontend most likely, per the charter)
- [x] Design + add a real "Cancelar" (discard checkpoint, one click)
- [x] Tests

### Phase 2 — Indeed Chrome window visibility
- [x] Fresh diagnosis (not a repeat of EATP-023's already-failed attempts)
- [x] Fix attempt — **still needs Kevin's live confirmation**
- [x] Tests (whatever is unit-testable — the GUI/WSLg part itself never is)

### Phase 3 — Verify & close
- [x] `pytest` green
- [x] Update ROADMAP status + total time
- [x] Write session notes below
- [x] Commit to git (CLAUDE.md §10) — one commit, clear message

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-16 | Fase 1 | ~15 min | Pausar/Cancelar: race-condition fix + nuevo botón, backend+frontend, 7 tests nuevos. |
| 2026-08-16 | Fase 2 | ~20 min | Diagnóstico en vivo con captura de logs de Chrome en el WSLg real de Kevin (no simulado) — confirmé `GPU.ContextLost` real y su desaparición con `--disable-gpu-compositing`. |
| 2026-08-16 | Fase 3 | ~5 min | Cierre: pytest verde, ROADMAP, commit. |

**Total project time:** ~40 min

## Session notes
**Pausar**: causa raíz encontrada por inspección de código, no reproducible literalmente sin el navegador real de Kevin — una condición de carrera: al hacer clic, el mensaje "Cancelando…" se mostraba, pero eventos normales de progreso que el pipeline sigue publicando mientras se detiene (hasta ~3 min en el peor caso) lo sobreescribían en 1-2 segundos, dando la sensación de que no pasó nada. Fix: una bandera `cancelling` en el frontend que congela el mensaje hasta que la corrida realmente termina.

**Cancelar**: nuevo botón, sin confirmación (decisión de Kevin). Reusa el mismo mecanismo de `/cancel`, con un flag `discard` nuevo en `cancellation.py` que, al capturarse `RunCancelled` en `pipeline.py`, además borra el checkpoint — así "Iniciar" arranca limpio en vez de retomar.

**Ventana de Indeed**: encontré algo que no se había probado en EATP-023 — lancé Chrome de verdad en el WSLg real de esta máquina (el mismo que usa Kevin) con `--enable-logging`/`--log-file` y capturé evidencia directa: `GPU.ContextLost.RendererCompositor`/`RendererRasterWorker` se disparaban en segundos con solo cargar `about:blank`, y el propio `GPU.BlocklistFeatureTestResults.GpuCompositing` de Chrome ya marca este hardware/driver como bloqueado para composición. Un contexto GPU perdido a mitad de sesión explica exactamente el síntoma que Kevin describió (ventana con marco pero sin pintar hasta que la clickea). Confirmé con un segundo run idéntico agregando `--disable-gpu-compositing`: cero eventos `ContextLost`. Apliqué la flag en `build_options()` — afecta a LinkedIn e Indeed por igual (comparten la función). **Sigue pendiente la confirmación visual de Kevin** — no hay forma de ver el lado Windows desde acá, pero por primera vez esta hipótesis está respaldada por telemetría real de Chrome capturada en su propia máquina, no solo teoría.
