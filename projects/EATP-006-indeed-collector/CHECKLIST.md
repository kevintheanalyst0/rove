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
| 2026-08-12 | Paralelismo (2 pestañas) + reverificación | ~20 min | A pedido de Kevin: la fase de detalle era muy lenta en secuencial |
| 2026-08-12 | Fix de espera en detalle + corrida completa (9 términos) | ~20 min | Kevin reportó "tarjetas vacías"; corregido y verificado a escala real |

**Total project time:** ~1.8 h (2026-08-12)

## Session notes
Reconstruido (no portado) sobre el framework: búsqueda secuencial de una sola pestaña
(barata, pocas páginas por término) + un pool de 2 pestañas en paralelo para la fase de
detalle, que es la que domina el tiempo total (una petición por vacante). Legacy usaba
2 de búsqueda + 3 de detalle coordinadas con locks/threads y bloqueaba TODO con
`input()` en cuanto cualquier pestaña topaba captcha. El JSON-LD se parsea de verdad
(`json.loads` sobre el `<script type="application/ld+json">`) en vez de regex sobre el
HTML crudo como hacía legacy. Captcha: por pedido explícito de Kevin, cero intervención
— se publica el evento solo para visibilidad, se reintenta una vez tras una pausa larga
(30-90s, tratando el captcha como señal de rate-limit, no de auth wall), y si persiste,
una bandera compartida (`threading.Event`) detiene TODAS las pestañas de una vez (el
bloqueo de Indeed es por sesión/IP, no por pestaña, así que más pestañas no empeoran
ese problema) y el resto de fuentes sigue sin verse afectado. Lo ya recolectado antes
del captcha se conserva (cada pestaña acumula sus éxitos en una cola compartida). Se
filtra solo con `criteria.title_is_rejected()` (título + empresa), igual que las demás
fuentes — el inglés avanzado y el remoto siguen centralizados en EATP-009.

**Verificación en vivo #1 (a petición de Kevin, no se cerraba sin esto):** corrida real
con un solo término ("analista de datos") contra Indeed real, diseño original de 1 sola
pestaña. Encontró un bug genuino: el JSON-LD real de Indeed usa el campo `datePosted`,
no `datePublished` (el nombre estándar de schema.org que asumía el charter) — con el
nombre equivocado, los 20 trabajos recolectados daban `days_old=999` para todos.
Corregido en `parse_detail_page()`; segunda corrida confirmó valores reales (0-22 días).

**Ajuste de paralelismo:** Kevin notó que ir "una vacante a la vez" era lento — con 1
término ya tardaba varios minutos; con los 9 términos de producción se habría ido a
10-20+ min solo para Indeed. Se agregó un pool de 2 pestañas para la fase de detalle
(Kevin eligió 2 de 3 opciones presentadas). **Verificación en vivo #2** con el diseño
paralelo: 1m 8s para el mismo término, 20 vacantes reales con `days_old` correctos
(0-22), descripciones completas, sin captcha en esta corrida.

**Fix de "tarjetas vacías":** Kevin reportó que en la fase de detalle a veces se abrían
páginas que parecían vacías o con mensajes tipo "no se encontró". Causa real: solo se
esperaba una pausa corta (1.5-4s) antes de leer el HTML de la página de detalle — si esa
página en particular tardaba más en renderizar (app pesada en JS, o 2 pestañas
compitiendo por recursos), se leía el HTML antes de que apareciera el JSON-LD o la
descripción, y la vacante se descartaba en silencio aunque era válida. Legacy sí tenía
esta espera explícita (`wait.ele_loaded(..., timeout=5)`) y la reconstrucción inicial la
omitió. Corregido: `_wait_for_detail_content()` espera hasta 5s a que aparezca
`#jobDescriptionText` antes de leer el HTML.

**Verificación en vivo #3 — corrida completa con los 9 términos de producción:**
6 minutos totales, sin ningún captcha. 55 ids únicos encontrados entre los 9 términos;
50 con JSON-LD utilizable, 5 (~9%) siguieron viniendo vacíos incluso con la espera —
consistente con vacantes genuinamente ya no disponibles (Indeed sirve una página de
"ya no disponible" para links expirados), no con el bug de timing original. 45 vacantes
reales al final, todas con descripción completa y `days_old` correcto. El camino de
reintento/abandono compartido entre pestañas sigue sin haberse visto en vivo (no hubo
captcha en ninguna de las 3 corridas reales) — solo está probado con los tests
scripteados con threading real; vale la pena vigilarlo cuando ocurra de forma natural
en una corrida programada.
