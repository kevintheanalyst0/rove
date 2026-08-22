# Scraping gotchas — lessons carried over from the legacy system

Kevin hit these problems building/running the legacy `jobmatch` collectors. They are
**not** captured anywhere else in the governance docs, so every collector project
(EATP-004 through 008) and the quality/dedup layer (EATP-009/010) must read this file.
Kevin's own words (paraphrased): *"casi en todos los sitios de empleo, al hacer
búsquedas, siempre vienen al final del todo vacantes recomendadas... hay que tener
cuidado de no incluir esas."* Treat the list below as **known problems, not an
exhaustive one** — when you build a new source (007/008) or refactor an existing one
(004/005/006), actively look for the same failure modes even if they're not named here,
and add what you find to this file.

---

## 1. "Recommended for you" jobs appended at the end of real results

Job sites pad the end of a results page with a recommendation/upsell block that is
**not part of the search results** — same markup as a real listing card, easy to
scrape by accident.

- **Confirmed on LinkedIn** (`legacy/jobmatch/collectors/linkedin.py::is_recommendation_card`):
  markers like *"empleos que podrían interesarte"*, *"principales empleos que te
  recomendamos"*, *"jobs you may be interested in"*, *"top job picks for you"*. The
  legacy collector stops consuming cards the moment one of these markers appears in a
  card's text, rather than trying to filter them out after the fact (a recommendation
  card can otherwise look identical to a real one).
- **Not yet confirmed, but likely** on any new source with a "for you" personalization
  feature (Indeed, OCC, Computrabajo, and especially Tier-1 boards if they ever add
  a logged-in view). **Action for EATP-004-008: check for this pattern on every new
  source**, even ones that seem to not have it — look at the raw HTML/JSON near the end
  of a results page/response before trusting "last N cards = real results".
- Detection strategy: prefer a structural signal (a distinct wrapper element/section,
  a different API field, a card index past `total_results`) over a keyword marker list
  when the site's markup allows it — keyword lists rot and are locale-specific (the
  Spanish and English phrasing both had to be listed for LinkedIn).

## 2. Pagination: sites differ in how you know you're done

Each site failed differently when the legacy code got pagination wrong. **A collector
must have a distinct "no more real results" signal for its own site** — don't assume
the same tactic still works when the site tweaks the fixed-page count.

- **OCC** (`occ.py`): fixed 2 pages per term, no real end-of-results detection. This
  may be silently under-fetching — **worth verifying/tightening in EATP-004** rather
  than porting the cap verbatim.
- **Computrabajo** (`computrabajo.py`): looks for a specific end-of-real-results HTML
  marker (`<div class="tc mbB pt30 pb30">`) and truncates the page's HTML there before
  parsing cards — anything after that marker is not a real result even mid-page.
- **LinkedIn** (historical — collector removed entirely in EATP-027; kept here as a
  documented pagination-detection technique, not a live source): read the
  total-results count from the page header text and stopped once `(page-1)*25`
  reached it; also stopped early if a page returned fewer than 25 cards
  (`< PAGE_SIZE`) — a partial page means it's the last one. Capped at
  `MAX_PAGES_PER_TERM = 10` as a safety net regardless.
- **Indeed** (`indeed.py`): stops when a page returns zero *new* ids, when a page
  returns fewer than `PAGE_SIZE` (10), **or** when the exact same tuple of ids repeats
  (`seen_page_signatures`) — this last one guards against a real failure mode: Indeed
  sometimes serves the same page twice instead of advancing, which without this check
  becomes an infinite loop. **Carry this loop-detection pattern into any new
  pagination code (007/008)**, not just Indeed — it's a general safety net, cheap to
  add, and the failure mode (infinite pagination) is a real crash/hang risk (CLAUDE.md
  §3).

## 3. Prefer the site's own search filters over filtering after the fact

Every legacy collector already does this, and it's a big lever for quality (P4) and
request budget (P5/quota): **push remote/recency/type filters into the search URL**
instead of fetching everything and discarding most of it client-side. When adding a new
source (007/008), look for the equivalent query params before writing any client-side
filter.

| Source | Filter params used | What they do |
|--------|--------------------|---------------|
| OCC | `/tipo-home-office-remoto/` (URL path segment) | Remote-only at the source |
| Computrabajo | `-en-remoto` (URL path suffix) | Remote-only at the source |
| LinkedIn *(historical, removed EATP-027)* | `f_WT=2` / `f_TPR=r86400` / `f_JT=F` / `sortBy=DD` | Remote / posted ≤24h / full-time / newest-first |
| Indeed | `fromage=14` / `sc=0kf:attr(DSQF7);` | Posted ≤14 days / remote attribute filter |

This doesn't replace the remote hard-gate (ADR-002) or recency check downstream — sites
occasionally mislabel a hybrid posting as remote — but it means far fewer irrelevant
jobs ever reach the parser, let alone the AI.

## 4. Duplicate jobs — three different problems, three different owners

Kevin's exact words: *"a veces hay vacantes repetidas, a veces las empresas publican la
misma vacante con diferente título, a veces la misma vacante puede salir en distintas
búsquedas."* These are three distinct failure modes with three different fixes —
don't solve them all the same way.

1. **Same posting scraped twice within one collector run** (e.g. a listing page
   glitch, or the same id appearing on two pages). Fix: a `seen_ids` set keyed on the
   site's own volatile id, checked **before** spending a detail request — cheap,
   collector-local, still correct to do in EATP-004-008. This is request-budget
   hygiene, not the real dedup layer.
2. **Same posting surfaces under two different search terms on the same source**
   (Kevin's example: "analista de datos" and "analista de negocios" both return the
   same vacancy). **This is deliberately NOT the collector's job in the new
   architecture** — ARCHITECTURE.md's data flow puts "fuzzy dedup within the run"
   downstream, in the quality layer (EATP-009/010), running over the *pooled* jobs from
   every term and every source together. A collector should yield every hit for every
   term as-is (after the cheap same-run id check in #1) and let EATP-010's fuzzy dedup
   catch the cross-term repeat — don't reintroduce legacy's per-collector
   title+description similarity check (`utils.py::is_duplicate`); it duplicates work
   EATP-010 already owns and, per point 3 below, doesn't even catch the harder case.
3. **Same posting, reworded with a different title** (a company reposts with a new
   headline but the same actual job). This is the dangerous one:
   - Content signature (ADR-001) hashes `company + title + description[:400]`. A
     changed title changes the signature, so the **cross-run cache will not recognize
     it as the same posting** (P9's fix doesn't fully cover this case).
   - Legacy's fuzzy dedup (`is_duplicate`) required **both** title similarity ≥ 0.90
     **and** description similarity ≥ 0.95 against the same company — so a materially
     different title made it fail the check too, and the "duplicate" got saved twice.
   - **EATP-010 must not repeat this mistake.** Company + description similarity is
     the strong signal; title should be *advisory*, the same way ADR-009 treats title
     everywhere else in the system — informative, never a required match condition for
     dedup. Weight the fuzzy-dedup comparison (rapidfuzz) so a high description
     similarity within the same company can flag a duplicate even when the title
     differs outright.

## 5. Other things worth carrying forward (not raised by Kevin, found while reading legacy code)

- **Rate-limit coordination across parallel browser tabs.** Indeed (and, until its
  removal in EATP-027, LinkedIn) runs several tabs in parallel and coordinates a
  *global pause* the moment any tab hits a captcha/429-like signal (one thread "wins"
  the pause, alerts, waits; the rest just wait on the same event) rather than each tab
  independently retrying and hammering the site harder. Relevant for any future
  multi-tab browser collector (EATP-030), not just Indeed.
- **Don't resurrect the "conditional title rescue" pattern.** Legacy's
  `filters.py::CONDITIONAL_TITLE_RULES` (e.g. reject "coordinator" unless a data/BI
  word is *also* in the title) is exactly the anti-pattern ADR-009 replaced after the
  "Analista administrativo" incident. When porting `legacy/jobmatch/collectors/filters.py`
  in EATP-009, keep the absolute exclusion list, drop the conditional-rescue logic —
  `criteria.title_caution_flags()` (EATP-002) already replaced it correctly.
- **A missing/empty description is a silent quality problem, not just a parsing bug**
  (P21) — Indeed's `get_job_details` and OCC's `_fetch_offer` both already treat an
  empty description as a reason to drop the job rather than pass along a job the AI
  can't meaningfully evaluate; keep that discipline in every new HTTP/browser
  collector.

## 5b. The persistent browser profile starts EMPTY — needs a one-time manual login

Discovered live in EATP-005 (LinkedIn's own collector, removed entirely in EATP-027 —
the lesson below stays relevant to Indeed and any future profile-using collector), not
something Kevin flagged in advance: `browser.py`'s `CHROME_USER_DATA_DIR` (EATP-003)
defaults to a brand-new directory under `data/` — unlike legacy, which pointed at an
existing, already-logged-in automation profile on Kevin's machine. The first live run
against LinkedIn with `use_profile=True` returned
**zero jobs with no error at all**: LinkedIn didn't redirect to `/login` or show any
health/error marker — it silently served the logged-out **public** search page instead
(different markup entirely: `base-search-card__title` instead of
`scaffold-layout__list-item`, no `data-occludable-job-id`, and it ignored the
`location=` search param). `is_login_page()` (URL-based) cannot catch this — the URL
never changes.

- **Any collector that turns on `use_profile=True` for the first time needs a manual,
  one-time, visible-browser login** before it will do anything useful — this is not
  optional setup, it's a hard prerequisite. In this WSL environment, a non-headless
  `build_page()` shows a real window via WSLg (`DISPLAY`/`WAYLAND_DISPLAY` are set) —
  use that to let Kevin log in once; the persistent profile dir keeps the session
  after that.
- **Relevant to EATP-006 (Indeed) too** if it reuses a persistent profile — check
  whether the profile has ever been logged into before assuming a browser-based
  collector "just works" on a fresh environment/machine.
- A logged-out **public** job-search view existing at all (rather than a hard
  authwall) is itself worth remembering: it's a plausible silent-failure mode for any
  LinkedIn-like site with a public SEO fallback — a health-check that only looks for
  error markers won't catch "successfully loaded the wrong, degraded page."

## 6. Fraudulent / ghost companies mass-posting to harvest data (P25)

Kevin's own words: *"hay muchas empresas fraudulentas, que anuncian cientos de empleos
distintos a diario... luego usan esas vacantes para robar datos de la gente. Esto
principalmente se logra ver en LinkedIn."* Real companies he's identified from the
legacy system: **BairesDev**, **Indi Staffing Services**. These are already in
`criteria.toml -> excluded_companies` (ported from legacy's `EXCLUDED_COMPANIES`) and
`criteria.is_excluded_company()` enforces the block — so the mechanism exists, but
**the list is almost certainly incomplete**; it only has the two companies Kevin
happened to remember.

- **This is a static blocklist, not a detector.** It only catches a fraudulent company
  by name, after Kevin has already identified it once. Treat it as a stopgap, not a
  solution: grow the list any time Kevin names a new offender, and when building
  EATP-009 (or later, EATP-013's matcher), consider whether a behavioral heuristic is
  worth adding on top — e.g. a company posting an implausibly large number of
  unrelated titles/locations within one run is itself a signal, independent of whether
  it's on the list yet. Don't build that heuristic speculatively before Kevin confirms
  it's worth the complexity; just don't design the gate so narrowly that a heuristic
  couldn't be added later.
- **Concentrated on LinkedIn** per Kevin, but don't assume other sources are immune —
  the same staffing-mill pattern (one "company" with hundreds of near-identical
  postings) can show up anywhere; watch for it when building 007/008 too.
- Traceability: added to `ROADMAP.md`'s problem list as **P25**.

## 7. Where a quality check lives: collector vs. centralized gate

Kevin correctly recalled that in the legacy system, filters like the English-required
check and the fraud-company check lived **inside each collector** (`occ.py`,
`computrabajo.py`, `indeed.py` all called `filters.title_is_rejected()` +
`filters.requires_advanced_english()`; `linkedin.py`'s `process_single_job()` called
`is_excluded_company`, `has_excluded_title`, `fails_conditional_title_rules`, and
`requires_advanced_english` directly, with its own slightly different order/set of
checks than the other three). That divergence — four collectors each deciding
filtering slightly differently — is itself a quality bug: it's how the same rule could
behave inconsistently by source. **Don't reproduce it.**

The rule for EATP-004-010, resolving the ambiguity:

- **May live in the collector, as a request-saving pre-filter (ADR-009):**
  `criteria.title_is_rejected()` — title + company only, absolute-category list only
  (this covers both the excluded-title-keywords check **and** the fraud-company
  check from §6, since a company name is normally visible on the listing card/search
  result before you'd fetch the full detail). This is the *only* filter allowed to run
  before a job's full description exists.
- **Must NOT live in the collector — centralize in EATP-009's `quality/filters.py`,
  run once over the pooled jobs from every source:** the English-requirement check
  (`classify_english_requirement_with_evidence`, EATP-028), `title_caution_flags()`
  (advisory, per ADR-009), the
  remote hard-gate, and any future junk/fraud heuristic beyond the static company
  list. None of these need to happen inside a collector — English detection in
  particular needs the full description, which means the detail request has already
  happened by the time you'd check it, so embedding it in the collector saves nothing
  and only reintroduces the four-different-implementations problem above.
- Site-native search filters (§3 of this file) are a third, separate thing — a URL
  query param, not app logic — and don't count as either of the above; keep using them
  freely, they reduce volume before any of this even applies.
