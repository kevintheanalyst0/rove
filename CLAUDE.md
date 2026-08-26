# CLAUDE.md — Operating Contract for Claude Code

> This file is the **single source of truth for how you (Claude Code) work in this
> repository.** Read it in full at the start of every session. It overrides your
> default habits. If anything here conflicts with a charter, this file wins unless
> the charter explicitly says otherwise.

---

## 0. Nota para Kevin (español)

Kevin no es desarrollador. Para trabajar, solo tiene que escribir algo como:

> **"Trabajemos en EATP-005"**

y tú haces el resto: lees el roadmap, cargas el contexto del proyecto, revisas
dependencias, y le devuelves **un plan con qué vas a construir, el tiempo estimado y
lo que te falte de él.** No construyes nada hasta que Kevin responda **"sigue"**.

Toda la **conversación con Kevin es en español.** Todo el **contenido del repo y el
código va en inglés.**

---

## 1. Mission

Rove is a **personal, remote-first job-discovery engine for Kevin.** Its job
is to surface **genuinely relevant, genuinely remote** Data Analyst / BI / Business
Analyst vacancies in the Spanish-speaking / LatAm market, evaluate them with AI, and
present the results in a clean local web UI — **with as few manual steps as possible.**

The north star is **quality of matches**, not volume. A short list Kevin actually
wants to apply to beats a long list he has to wade through.

Read `docs/governance/CANDIDATE-PROFILE.md` to understand who Kevin is and what
"a good job for Kevin" means. Read `docs/diagnosis/LEGACY-SYSTEM-REVIEW.md` to
understand what the old system did and why we are rebuilding it.

---

## 2. Golden rules (non-negotiable)

1. **One project per session.** You work on exactly one `EATP-00X` per session. Do
   not wander into other projects. This keeps context small and cheap.
2. **Never use subagents, the Task tool, or any form of parallel agent delegation.**
   You build everything yourself, in the main thread. No exceptions.
3. **Guard against out-of-memory crashes.** Before any heavy operation (large loops,
   big file writes, scraping many pages, loading big JSON), estimate memory. Stream,
   chunk, and write block-wise. Checkpoint between heavy stages. **If you sense an
   imminent crash risk, STOP, tell Kevin, and re-plan that part** — do not push
   through. This happened repeatedly in the Bramvel project; do not repeat it.
4. **Plan first, build after "sigue".** See §3 (Session Protocol). Never start
   building on the first message of a session.
5. **Phased delivery with confirmation.** Build in visible phases. After each phase,
   summarize what changed and wait for Kevin's confirmation before the next phase.
6. **Track progress with checkboxes and time.** Keep the project's `CHECKLIST.md`
   updated live (`[ ]` → `[x]`) and log elapsed time. See §5.
7. **Decide technical things yourself; ask Kevin only product/architecture questions.**
   See §6. Kevin cannot answer "which library" or "why does this import fail" — those
   are yours. Ask him only what a non-developer can reasonably decide.
8. **Protect the Gemini / AI quota.** Free AI tiers are tiny (Gemini 2.5 Flash ≈ 20
   calls/day). **Never spend live AI calls on tests.** Tests use recorded fixtures.
   See §7.
9. **The product is a web page, not a terminal.** The end experience Kevin sees is a
   browser with a Windows-style dots spinner + status text, then results. The terminal
   is only for you while building. See ADR-004.
10. **Repo/code in English, conversation in Spanish.** Always.
11. **Never commit secrets or runtime data.** `.env` and `data/` are gitignored.
    GitHub publish happens only in EATP-018, only after Kevin approves.
12. **Legacy code is reference material, never a default to port.** Every project with
    a `legacy/` file in its "Context to load" (004-010+) must be judged on its own
    merits against the two non-negotiable premises — **speed** and **quality of
    results** (§1: few excellent matches, not hundreds of mediocre ones), never
    "volume of vacancies found." Rebuild from scratch if the legacy approach doesn't
    hold up against those premises; keep and adapt it only where you determine it's
    genuinely the right design. State that rebuild-vs-keep verdict explicitly in the
    session's plan (§3 Step C) — don't silently port-and-tweak out of habit.

---

## 3. Session Protocol

When Kevin says **"Trabajemos en EATP-00X"** (or similar), do this, in order:

**Step A — Orient (silent, cheap).**
1. Open `ROADMAP.md`. Confirm EATP-00X exists, is not blocked, and its dependencies
   (earlier EATP projects) are marked ✅ Done. If a dependency is not done, tell Kevin
   and propose working on the correct project instead.
2. Open `projects/EATP-00X/CHARTER.md`. Read it fully.
3. Load **only** the files listed in the charter's **"Context to load"** table.
   Do not read the whole repo. This is the token-discipline mechanism — respect it.
4. Skim `projects/EATP-00X/CHECKLIST.md` if it already has progress (a resumed
   project).

**Step B — Verify readiness.**
5. Check `docs/governance/DEPENDENCIES.md`. Verify which required tools/libraries are
   already installed (`pip show ...`, `python -c "import ..."`). Note what is missing.
6. If the charter has **"Open questions for Kevin"**, collect them.

**Step C — Return the plan and STOP.** Reply to Kevin (in Spanish) with:
   - **Legacy: reconstruir o conservar** — if the charter has a `legacy/` reference
     file, your verdict on it (golden rule 12) and why, before anything else.
   - **Qué voy a construir** — a short, concrete list of what this session will produce.
   - **Fases** — the phases you'll go through (maps to the checklist).
   - **Tiempo estimado** — your honest estimate.
   - **Dependencias** — what's already installed vs. what needs installing (and ask
     permission to install anything new — see §8).
   - **Lo que necesito de ti** — anything missing: files, decisions, credentials Kevin
     must provide, or the open questions. **Add anything you notice is missing that
     Kevin didn't think of.**
   - Then **wait.** Do not build.

**Step D — Build (only after "sigue").** Work through the phases. Keep the checklist
   and time log updated. Confirm between phases.

**Step E — Close the project.** When done (see §9, Definition of Done):
   - Tick every checkbox, finalize the time log.
   - Update `ROADMAP.md`: set EATP-00X status to ✅ Done with the completion date and
     total time.
   - Write a 3–6 line summary in `projects/EATP-00X/CHECKLIST.md` under "Session notes".
   - **Commit the project's changes to git** (§10). This is a required closing step,
     not optional — a project is not Done until it is committed. If the repo has no
     `.git` yet, `git init` it first (once), don't skip the commit because of that.
   - Tell Kevin it's done and what the next recommended project is.

---

## 4. How to read a charter

Every `CHARTER.md` has the same sections:
- **Objective** — what & why.
- **Problems solved** — traceability to Kevin's original problem list (P1…P16).
- **Context to load** — the *only* files you should read this session.
- **Dependencies** — EATP projects that must be done first; libraries needed.
- **Scope: In / Out** — build what's In; do not build what's Out (that's a later project).
- **Deliverables** — the concrete artifacts this session must produce.
- **Key design decisions & constraints** — site-specific gotchas, the "do it this way".
- **Definition of Done** — the checklist for "this project is finished".
- **Estimated time**.
- **Open questions for Kevin** — surface these in your plan.

---

## 5. Progress & time tracking

Each project owns `projects/EATP-00X/CHECKLIST.md`. It contains:
- A **phased checklist** of `[ ]` items. Tick them (`[x]`) as you complete them, in
  real time, so Kevin can see exactly where you are and how much is left.
- A **time log** table. Record the wall-clock start of the project, the time each
  phase took, and a cumulative total. At the end, write the **total project time** so
  Kevin can compare which project took longest.

Use real timestamps. If a session is resumed on another day, add a new time-log row;
do not overwrite. The total is the sum of all sessions on that project.

---

## 6. When to ask Kevin vs. decide yourself

**Decide yourself (do NOT ask):** library choice, code structure, file naming,
how to fix an import error or a bug in an earlier project, retry logic, how to parse a
site, test design, refactors, performance tradeoffs, anything that requires developer
judgment. If an earlier EATP project has a bug that blocks you, **fix it** and note it.

**Ask Kevin (one question at a time, in Spanish):** product/architecture decisions a
non-developer can reason about, e.g. "¿Descartamos del todo las vacantes híbridas o
las mostramos marcadas?", "¿Prefieres priorizar velocidad o exhaustividad en esta
corrida?", or anything needing his credentials, his accounts, or a judgment about his
own preferences/career. When in doubt about whether it's his call: if it changes *what
the product does for him*, ask; if it's *how the code achieves it*, decide.

---

## 7. AI / Gemini quota discipline

- Free AI tiers are small and volatile. Treat every live call as scarce. A `503` still
  consumes a Gemini call.
- **Tests never call live AI.** Use the recorded fixtures in `tests/fixtures/` and
  mock the provider. Build and verify the whole AI layer offline.
- The only acceptable live AI call during development is a **single tiny smoke test**,
  and only **after Kevin explicitly approves it** in that session.
- See `docs/governance/AI-PROVIDERS.md` for the multi-provider strategy (Groq /
  Gemini Flash-Lite / others) and the fallback order that makes quota far less painful.

---

## 8. Dependency protocol

- The master list lives in `docs/governance/DEPENDENCIES.md`. At project start, check
  what's already installed before installing anything.
- If a project needs a **new** dependency not in the master list: **announce it to
  Kevin, say what it's for, and get a "sí" before installing.** Then add it to
  `DEPENDENCIES.md` and to `pyproject.toml` / `requirements.txt`.
- Prefer well-maintained, widely-used libraries. Avoid anything that requires Kevin to
  manually configure system-level tooling unless unavoidable (then explain it simply).
- Before running any command that has side effects, state in one line **what it does
  and why** (Kevin has asked not to run commands he doesn't understand).

---

## 9. Definition of Done (per project)

A project is Done only when ALL of these hold:
- [ ] Every deliverable in the charter exists and works.
- [ ] `pytest` passes for this project's tests (green), using fixtures, no live AI.
- [ ] No known crash / OOM risk left unaddressed.
- [ ] The checklist is fully ticked and the time log is finalized.
- [ ] `ROADMAP.md` status is updated to ✅ Done (date + total time).
- [ ] A short "Session notes" summary is written.
- [ ] **The project's changes are committed to git** (one commit per project, clear
      message — see §10). Kevin expects every finished project to already be committed
      when he next opens the repo; don't leave this for a later session.
- [ ] Nothing secret or heavy was committed (verify `.gitignore` still covers it).

---

## 10. Git & GitHub

- Develop on the local repo inside Ubuntu/WSL. **Commit per project with clear
  messages** (e.g. `EATP-010: content-signature cache + run history`) — this is
  enforced by §3 Step E and §9's Definition of Done, not a nice-to-have. Kevin's
  expectation is that a project he's told is "Done" is already committed; don't make
  him ask.
- **Do not push to GitHub until EATP-018**, and only after Kevin approves. When you do,
  double-check `.gitignore` excludes `.env`, `data/`, browser profiles, and any
  personal artifacts (CV files, cover letters, cookies).

---

## 11. Communication style with Kevin

- Spanish, direct, concrete. Deliver working things, not essays.
- Lead with the answer / the plan. Keep caveats short.
- One question per message when you must ask.
- Don't over-explain technical internals unless he asks; he trusts your judgment on
  the "how".
