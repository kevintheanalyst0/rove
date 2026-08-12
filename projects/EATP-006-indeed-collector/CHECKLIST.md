# EATP-006 — Indeed collector — optimize & reduce captchas — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Stealth + pacing
- [x] stealthier browser config (reuses `browser.build_page`/`human_pause` from EATP-003)
- [x] human pacing
- [x] session reuse (persistent profile, same as LinkedIn's)

### Phase 2 — Parsing
- [x] search ids (+ pagination loop-detection carried from legacy)
- [x] JSON-LD details (real `json.loads` on the `JobPosting` script block)
- [x] remote filter (`sc=0kf:attr(DSQF7)` URL param, site-native — SCRAPING-GOTCHAS.md §3; `Job.remote_status` stays UNKNOWN, same as LinkedIn — EATP-009 owns the hard-gate)
- [x] fixture tests (`tests/fixtures/indeed_jobs.json`, real records)

### Phase 3 — Captcha handling
- [x] detect + event + isolate Indeed
- [x] non-blocking pause/skip (one retry after long cooldown, then clean stop — never `input()`, never waits on Kevin)
- [x] captcha-page test (synthetic captcha response via scripted fake page; recovery path + persistent-captcha path + partial-progress-preserved path)

### Phase 4 — Close
- [x] register as first-class (satisfies `Collector` protocol; no feature flag to disable it — same as LinkedIn's approach, real registry wiring is EATP-014's job)
- [x] pytest (140 passed, whole suite)
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Fases 1-4 | ~45 min | Sin diagnóstico de login (Indeed no requiere sesión) — más simple que EATP-005 |

**Total project time:** ~45 min (2026-08-12)

## Session notes
Reconstruido (no portado) sobre el framework: una sola pestaña secuencial (legacy usaba
2 de búsqueda + 3 de detalle coordinadas con locks/threads — mismo riesgo de cuenta y
complejidad que se evitó en LinkedIn). El JSON-LD se parsea de verdad
(`json.loads` sobre el `<script type="application/ld+json">`) en vez de regex sobre el
HTML crudo como hacía legacy. Captcha: por pedido explícito de Kevin, cero intervención
— se publica el evento solo para visibilidad, se reintenta una vez tras una pausa larga
(30-90s, tratando el captcha como señal de rate-limit, no de auth wall), y si persiste,
Indeed se detiene limpiamente para esa corrida sin bloquear las demás fuentes. Como
`collect()` transmite cada `Job` en cuanto se construye, lo ya recolectado antes del
captcha nunca se pierde. Se filtra solo con `criteria.title_is_rejected()` (título +
empresa), igual que las demás fuentes — el inglés avanzado y el remoto siguen
centralizados en EATP-009. No se probó en vivo (a diferencia de LinkedIn, esta sesión
no lo requería para completar el charter); la primera corrida real conviene vigilarla
por si el timing del captcha necesita un ajuste, tal como el charter ya anticipaba.
