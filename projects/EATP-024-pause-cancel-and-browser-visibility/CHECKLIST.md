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
- [x] Fix attempt — **live-verified by Kevin (2026-08-16): window now appears reliably**
- [x] Tests (whatever is unit-testable — the GUI/WSLg part itself never is)

### Phase 1b — Real-run report: Pausar/Cancelar still didn't stop the run
- [x] Live-checked Kevin's actual running server (same machine) via `/status` + checkpoint —
      confirmed collect ran through every remaining source and into AI scoring untouched
- [x] Found the real gap: `pipeline.py` only checks cancellation *between* whole sources;
      every HTTP collector's own loop (companies/pages/terms) had zero check of its own,
      and `run_collector()`'s broad `except Exception` doesn't stop that from working
      correctly one iteration later — but a single source can take 1-2 min uninterrupted
- [x] Added `cancellation.check()` inside the collect loops of greenhouse, lever,
      computrabajo (page + card level), himalayas, remotive, occ (both id-listing and,
      for the `ThreadPoolExecutor` detail-fetch phase, a manual non-blocking
      `shutdown(wait=False, cancel_futures=True)` instead of the `with` block's default
      blocking wait)
- [x] Found and fixed the bigger gap: the AI-evaluation phase had no way to abandon a
      slow/hung call at all — added `_evaluate_batch_cancellable` (pipeline.py), running
      each AI batch in a background thread and polling every 0.5s, so Pausar/Cancelar
      no longer waits out AI_MAX_RETRIES x AI_REQUEST_TIMEOUT_SECONDS (~3 min worst case)
- [x] Tests: cancellation-mid-loop tests for greenhouse/lever/occ, plus a genuinely
      hung-forever AI provider test proving cancellation lands in well under 3s

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
| 2026-08-16 | Fase 1b | ~25 min | Kevin reportó en vivo que ni Pausar ni Cancelar frenaban una corrida real — encontré que los collectors HTTP no tenían ningún chequeo de cancelación dentro de su propio loop, y que la fase de IA no tenía forma de abandonar una llamada lenta/colgada. Arreglado en ambos frentes, con tests. |
| 2026-08-16 | Fase 3 | ~10 min | Cierre: pytest verde, ROADMAP, commit. |
| 2026-08-16 | Fase 1c | ~10 min | Kevin probó una corrida real: confirmé en vivo (curl directo, no su clic) que Cancelar detiene la corrida en 1.8s. Sus propios clics seguían sin reaccionar — causa: Edge reutilizaba una sesión vieja con el JS anterior; un hard-refresh (Ctrl+Shift+R) lo resolvió. Guardado como memoria para futuras sesiones. |
| 2026-08-16 | Fase 4 | ~5 min | Kevin confirmó en vivo que la ventana de Indeed/LinkedIn ahora aparece bien. Cierre final del proyecto. |

**Total project time:** ~1h25min

## Session notes
**Pausar (primera vuelta)**: causa raíz encontrada por inspección de código — una condición de carrera de frontend: al hacer clic, el mensaje "Cancelando…" se mostraba, pero eventos normales de progreso lo sobreescribían en 1-2 segundos. Fix: bandera `cancelling` que congela el mensaje.

**Pausar/Cancelar (segunda vuelta, en vivo)**: ese fix no era suficiente — Kevin probó con una corrida real y ni Pausar ni Cancelar frenaban nada; revisé su servidor real (corriendo en esta misma máquina) y confirmé que la corrida siguió de largo por todas las fuentes restantes sin detenerse. Causa raíz real: `pipeline.py` solo revisa cancelación *entre* fuentes completas — ningún collector HTTP (greenhouse, lever, computrabajo, occ, himalayas, remotive) revisaba nada dentro de su propio loop de páginas/empresas/términos, así que un clic podía quedar "atrapado" hasta que toda esa fuente terminara (1-2 min). Peor aún: la fase de evaluación con IA no tenía ninguna forma de abandonar una llamada lenta o colgada — ahí sí podía tardar hasta ~3 min real. Arreglé ambos: chequeos de cancelación dentro de cada collector HTTP, y una nueva `_evaluate_batch_cancellable` en `pipeline.py` que corre cada lote de IA en un hilo aparte y lo abandona (no lo espera) en cuanto se pide cancelar — verificado con un test que cuelga la IA para siempre y confirma que igual cancela en menos de 3 segundos.

**Cancelar**: nuevo botón, sin confirmación (decisión de Kevin). Reusa el mismo mecanismo de `/cancel`, con un flag `discard` nuevo en `cancellation.py` que, al capturarse `RunCancelled` en `pipeline.py`, además borra el checkpoint — así "Iniciar" arranca limpio en vez de retomar.

**Ventana de Indeed**: encontré algo que no se había probado en EATP-023 — lancé Chrome de verdad en el WSLg real de esta máquina (el mismo que usa Kevin) con `--enable-logging`/`--log-file` y capturé evidencia directa: `GPU.ContextLost.RendererCompositor`/`RendererRasterWorker` se disparaban en segundos con solo cargar `about:blank`, y el propio `GPU.BlocklistFeatureTestResults.GpuCompositing` de Chrome ya marca este hardware/driver como bloqueado para composición. Un contexto GPU perdido a mitad de sesión explica exactamente el síntoma que Kevin describió (ventana con marco pero sin pintar hasta que la clickea). Confirmé con un segundo run idéntico agregando `--disable-gpu-compositing`: cero eventos `ContextLost`. Apliqué la flag en `build_options()` — afecta a LinkedIn e Indeed por igual (comparten la función). **Kevin confirmó en vivo (2026-08-16) que la ventana ahora aparece bien** — primera vez en todo el ciclo EATP-023/024 que este problema queda resuelto y no solo teorizado.

**Cierre**: los tres puntos del Definition of Done quedaron live-verificados por Kevin en la misma sesión: Pausar reacciona visiblemente, Cancelar descarta el checkpoint en un clic (~1-2s), y la ventana de Indeed/LinkedIn aparece de forma confiable. Nada quedó pendiente.
