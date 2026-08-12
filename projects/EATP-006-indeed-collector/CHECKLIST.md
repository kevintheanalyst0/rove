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
| 2026-08-12 | Verificación en vivo | ~15 min | Encontró y corrigió un bug real (ver notas) |

**Total project time:** ~1 h (2026-08-12)

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
centralizados en EATP-009.

**Verificación en vivo (a petición de Kevin, no se cerraba sin esto):** corrida real
con un solo término ("analista de datos") contra Indeed real. Encontró un bug genuino:
el JSON-LD real de Indeed usa el campo `datePosted`, no `datePublished` (el nombre
estándar de schema.org que asumía el charter) — con el nombre equivocado, los 20
trabajos recolectados daban `days_old=999` para todos. Corregido en
`parse_detail_page()`; segunda corrida confirmó valores reales (0-22 días). Títulos,
empresas y descripciones completas y plausibles en los 20 casos, sin captcha en esta
corrida (así que el camino de reintento/abandono solo quedó probado con los tests
scripteados, no en vivo — vale la pena vigilarlo en la primera corrida programada real,
tal como ya anticipaba el charter).
