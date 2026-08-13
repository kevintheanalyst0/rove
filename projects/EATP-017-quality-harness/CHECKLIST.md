# EATP-017 — Match-quality evaluation harness — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Labeling
- [x] capture a run's shown jobs
- [x] label good/bad
- [x] store labels

### Phase 2 — Metrics
- [x] precision + FP-by-reason
- [x] baseline snapshot
- [x] tests

### Phase 3 — Close
- [x] report summary
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | 1-3 | ~35 min | Single session, all phases |

**Total project time:** ~35 min

## Session notes
Labeling flow reutiliza el modal de detalle del dashboard (EATP-016): botones "Buena"/"Mala" +
chips de razón (no remoto/fuera de campo/inglés/otro), persistidos en `data/eval/labels.jsonl`
(mismo patrón append-only que `tracking/store.py`). `eval/report.py` calcula
`precision@shown` + desglose de falsos positivos por razón y compara contra un baseline
guardado en `data/eval/baseline.json` (se corre como script: `python -m career_radar.eval.report`,
`--set-baseline` para reanclar después de un ajuste). Bug encontrado y corregido durante
verificación manual: una corrida sin ninguna etiqueta no debe fijar un baseline vacío
(bloquearía que el primer baseline real se guarde). Falta que Kevin etiquete una docena+
de vacantes reales desde el dashboard para que el reporte tenga señal.
