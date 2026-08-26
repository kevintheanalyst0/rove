"""scoring/{prefilter,evaluate,validate} — Layers 2-4 (EVALUATION-RUBRIC.md).
AI is always mocked via a scripted `Provider`; never a live call (CLAUDE.md §7).
"""

from __future__ import annotations

from rove.ai.base import AiResult, Provider
from rove.ai.router import AiRouter
from rove.ai.usage import UsageTracker
from rove.criteria import (
    Criteria,
    EnglishRequirementCriteria,
    Matcher,
    RemoteSignals,
    ScoreFloors,
    load_criteria,
)
from rove.models import EnglishRequirement, Grade, Job, RemoteStatus, ScoredJob
from rove.profile import load_profile
from rove.scoring import rank_scored_jobs, score_jobs
from rove.scoring.evaluate import build_deferred, evaluate_selected
from rove.scoring.prefilter import prefilter_score, run_prefilter
from rove.scoring.validate import strip_contradictions, validate, validate_all

PROFILE = load_profile()


def _job(
    *,
    source_job_id: str = "1",
    title: str = "Data Analyst",
    description: str = "x" * 250,
    remote_status: RemoteStatus = RemoteStatus.REMOTE,
    days_old: int = 999,
    english_requirement: EnglishRequirement = EnglishRequirement.COMPATIBLE,
) -> Job:
    return Job(
        source="test",
        source_job_id=source_job_id,
        title=title,
        description=description,
        url=f"http://example.com/{source_job_id}",
        remote_status=remote_status,
        days_old=days_old,
        english_requirement=english_requirement,
    )


def _criteria(
    *,
    role_weights: dict[str, int] | None = None,
    skill_weights: dict[str, int] | None = None,
    remote_bonus: int = 20,
    recency_bonus: list[tuple[int, int]] | None = None,
    prefilter_reject_floor: int = 20,
    ai_cap_top_n: int = 50,
    title_caution_words: dict[str, list[str]] | None = None,
) -> Criteria:
    """A minimal, self-contained `Criteria` for tests that exercise the
    pre-filter's mechanics in isolation from `criteria.toml`'s real weights
    (which are free to be re-tuned later without breaking these)."""
    return Criteria(
        excluded_companies=[],
        excluded_title_keywords={},
        title_caution_words=title_caution_words or {},
        english_requirement=EnglishRequirementCriteria(
            reject_phrases=[], reject_regex=[], indeterminate_phrases=[], indeterminate_regex=[]
        ),
        remote_signals=RemoteSignals(
            positive_phrases=["remote", "remoto"],
            hybrid_phrases=["hybrid", "híbrido"],
            onsite_phrases=["onsite", "presencial"],
            onsite_per_week_regex=r"(\d+)\s*days?\s*a\s*week",
            onsite_per_month_regex=r"(\d+)\s*days?\s*a\s*month",
            onsite_per_week_regex_en=r"(\d+)\s*days?\s*a\s*week",
            onsite_per_month_regex_en=r"(\d+)\s*days?\s*a\s*month",
            max_onsite_days_per_month=1,
        ),
        matcher=Matcher(
            role_weights=role_weights or {"data analyst": 30, "business intelligence": 40},
            skill_weights=skill_weights or {"Power BI": 25, "SQL": 25},
            remote_bonus=remote_bonus,
            recency_bonus=recency_bonus or [(7, 10)],
            score_floors=ScoreFloors(
                prefilter_reject_floor=prefilter_reject_floor, ai_cap_top_n=ai_cap_top_n
            ),
        ),
    )


class ScriptedProvider(Provider):
    """Returns `results_by_signature[job.signature]` per job given (nothing
    for a signature not in the script — simulating the AI omitting a job),
    plus any `extra` results tacked on regardless of what was asked for
    (simulating a hallucinated/invented id)."""

    def __init__(
        self, results_by_signature: dict[str, AiResult], *, extra: list[AiResult] | None = None
    ) -> None:
        self.id = "scripted"
        self._by_sig = results_by_signature
        self._extra = extra or []
        self.batches: list[list[Job]] = []

    def evaluate_batch(self, jobs: list[Job], profile) -> list[AiResult]:
        self.batches.append(jobs)
        matched = [self._by_sig[job.signature] for job in jobs if job.signature in self._by_sig]
        return [*matched, *self._extra]


def _router(results_by_signature: dict[str, AiResult], *, extra: list[AiResult] | None = None) -> AiRouter:
    provider = ScriptedProvider(results_by_signature, extra=extra)
    return AiRouter({"scripted": provider}, order=["scripted"], usage=UsageTracker())


# ---------------------------------------------------------------------------
# Layer 2 — pre-filter: score, reject, cap
# ---------------------------------------------------------------------------


def test_prefilter_score_sums_role_skill_remote_and_recency_weights():
    criteria = _criteria()
    job = _job(title="Data Analyst", description="Use Power BI and SQL daily." + "x" * 200, days_old=3)
    # 30 (role) + 25 + 25 (skills) + 20 (remote) + 10 (recency) = 110, clamped to 100.
    assert prefilter_score(job, criteria) == 100


def test_prefilter_rejects_a_finance_intern_with_no_role_or_skill_signal():
    criteria = _criteria()
    job = _job(
        title="Finance Intern",
        description="Support the finance team with budgeting and accounts payable in Excel." + "x" * 150,
        remote_status=RemoteStatus.UNKNOWN,
    )
    outcome = run_prefilter([job], criteria)
    assert job in outcome.rejected
    assert outcome.scores[job.signature] < criteria.matcher.score_floors.prefilter_reject_floor


def test_prefilter_caps_survivors_to_top_n_best_first_and_defers_the_rest():
    criteria = _criteria(ai_cap_top_n=2)
    strong = _job(source_job_id="1", title="Business Intelligence Analyst", description="Power BI and SQL." + "x" * 200)
    medium = _job(source_job_id="2", title="Data Analyst", description="x" * 250)
    weak = _job(source_job_id="3", title="Data Analyst", description="x" * 250, remote_status=RemoteStatus.UNKNOWN)

    outcome = run_prefilter([weak, medium, strong], criteria)

    assert outcome.selected == [strong, medium]
    assert outcome.deferred == [weak]
    assert outcome.rejected == []


def test_unrescued_title_caution_flag_applies_a_small_penalty():
    criteria = _criteria(title_caution_words={"administrator": ["data", "power bi"]})
    unrescued = _job(
        title="Systems Administrator",
        description="Manage servers and network infrastructure daily." + "x" * 150,
    )
    rescued = _job(
        source_job_id="2",
        title="Systems Administrator",
        description="Manage data pipelines and dashboards daily." + "x" * 150,
    )
    assert prefilter_score(unrescued, criteria) == 15  # 20 remote - 5 penalty
    assert prefilter_score(rescued, criteria) == 20  # description confirms it -> no penalty


# ---------------------------------------------------------------------------
# ADR-009 — title is a signal, never a verdict. Uses the REAL criteria.toml,
# since these tests exist to prove the production rubric data behaves.
# ---------------------------------------------------------------------------


def test_bland_title_with_strong_bi_description_scores_well_despite_the_title():
    # ADR-009's motivating case: "Analista administrativo" looked unremarkable
    # on title alone and got buried by the legacy system; the description is
    # genuinely a strong BI role and must score accordingly.
    job = _job(
        title="Analista administrativo",
        description=(
            "Responsable de construir y mantener dashboards de Power BI, "
            "escribir consultas SQL complejas, automatizar reportes y dar "
            "soporte a la toma de decisiones del área comercial mediante "
            "Business Intelligence." + "x" * 100
        ),
    )
    criteria = load_criteria()
    assert prefilter_score(job, criteria) >= 70
    outcome = run_prefilter([job], criteria)
    assert job in outcome.selected


def test_friendly_title_hiding_off_field_work_is_not_waved_through_by_layer3():
    # Mirror case: a "Data Analyst" title over a Linux/DBA-heavy body. Layer 2
    # alone can't rule it out (the title keyword and remote bonus still
    # apply) — the real protection is Layer 3's hard cap, simulated here via
    # a mocked AI score honoring EVALUATION-RUBRIC.md's excluded-field cap.
    job = _job(
        title="Data Analyst",
        description=(
            "Administrarás servidores Linux, bases de datos Oracle en "
            "producción, tareas de DBA, tuning de queries a bajo nivel y "
            "soporte de infraestructura on-call, guardias 24/7." + "x" * 100
        ),
    )
    criteria = load_criteria()
    outcome = run_prefilter([job], criteria)
    assert job in outcome.selected  # Layer 2 can't rule this out from title/remote alone

    router = _router(
        {job.signature: AiResult(signature=job.signature, ai_score=15, summary="Rol de infraestructura, no de BI.")}
    )
    scored = evaluate_selected(outcome.selected, outcome.scores, router, PROFILE)
    validated = validate_all(scored, criteria)

    assert validated[0].final_score == 15
    assert validated[0].grade == Grade.D


# ---------------------------------------------------------------------------
# Layer 3 — AI evaluate: id-based assembly, never positional
# ---------------------------------------------------------------------------


def test_evaluate_selected_assembles_one_scored_job_per_job_in():
    job = _job()
    router = _router({job.signature: AiResult(signature=job.signature, ai_score=77, pros=["Buen fit"], summary="ok")})
    [scored] = evaluate_selected([job], {job.signature: 40}, router, PROFILE)
    assert scored.ai_evaluated is True
    assert scored.final_score == 77
    assert scored.pros == ["Buen fit"]


def test_missing_ai_result_falls_back_to_prefilter_score_never_crashes():
    job_a = _job(source_job_id="a", title="Data Analyst")
    job_b = _job(source_job_id="b", title="BI Analyst")
    router = _router({job_a.signature: AiResult(signature=job_a.signature, ai_score=77, summary="ok")})

    scored = evaluate_selected([job_a, job_b], {job_a.signature: 40, job_b.signature: 35}, router, PROFILE)
    by_sig = {item.job.signature: item for item in scored}

    assert by_sig[job_a.signature].ai_evaluated is True
    assert by_sig[job_a.signature].final_score == 77
    assert by_sig[job_b.signature].ai_evaluated is False
    assert by_sig[job_b.signature].final_score == 35


def test_invented_ai_id_is_dropped_never_misattributed_to_the_wrong_job():
    job = _job()
    invented = AiResult(signature="not-a-real-signature", ai_score=99, summary="hallucinated")
    router = _router({job.signature: AiResult(signature=job.signature, ai_score=60)}, extra=[invented])

    [scored] = evaluate_selected([job], {job.signature: 40}, router, PROFILE)

    assert scored.final_score == 60  # never picks up the invented job's score


def test_build_deferred_never_calls_the_ai():
    job = _job()
    deferred = build_deferred([job], {job.signature: 45})
    assert deferred[0].ai_evaluated is False
    assert deferred[0].final_score == 45


def test_indeterminate_english_is_flagged_confirm_english_even_without_ai():
    # P27: a job the AI cap defers (never reaches evaluate_selected) must
    # still surface the flag — Kevin can't confirm what he never sees.
    job = _job(english_requirement=EnglishRequirement.INDETERMINATE)
    [deferred] = build_deferred([job], {job.signature: 45})
    assert "confirm_english" in deferred.flags


def test_indeterminate_english_is_flagged_confirm_english_when_ai_evaluated():
    job = _job(english_requirement=EnglishRequirement.INDETERMINATE)
    router = _router({job.signature: AiResult(signature=job.signature, ai_score=77, summary="ok")})
    [scored] = evaluate_selected([job], {job.signature: 40}, router, PROFILE)
    assert "confirm_english" in scored.flags


# ---------------------------------------------------------------------------
# Layer 4 — post-validation guards
# ---------------------------------------------------------------------------


def test_high_score_with_empty_contras_stays_consistent_not_contradictory():
    job = _job(
        title="Business Intelligence Analyst",
        description="Puesto 100% remoto. Power BI, SQL, gran encaje." + "x" * 150,
    )
    scored = ScoredJob(
        job=job, prefilter_score=80, prefilter_passed=True, ai_evaluated=True, ai_score=93, pros=["Gran encaje"]
    )
    validated = validate(scored)
    assert validated.contras == []
    assert validated.grade == Grade.A_PLUS
    assert validated.flags == []


def test_remote_recheck_demotes_and_flags_a_high_score_job_that_reads_non_remote():
    job = _job(
        title="Data Analyst",
        description="Puesto presencial en CDMX, reportes de ventas en Excel." + "x" * 150,
        remote_status=RemoteStatus.REMOTE,  # e.g. a stale/mis-set upstream field
    )
    scored = ScoredJob(job=job, prefilter_score=50, prefilter_passed=True, ai_evaluated=True, ai_score=92)
    validated = validate(scored)
    assert validated.final_score <= 79
    assert validated.grade not in (Grade.A_PLUS, Grade.A)
    assert "remote_uncertain" in validated.flags


def test_english_recheck_demotes_and_flags_a_high_score_job_requiring_advanced_english():
    job = _job(
        title="Data Analyst",
        description=(
            "Puesto 100% remoto. Se requiere inglés avanzado para reuniones "
            "diarias con el equipo global." + "x" * 150
        ),
    )
    scored = ScoredJob(job=job, prefilter_score=50, prefilter_passed=True, ai_evaluated=True, ai_score=95)
    validated = validate(scored)
    assert validated.final_score <= 79
    assert "english_required" in validated.flags


def test_english_recheck_never_demotes_for_ambiguous_indeterminate_phrasing():
    # P27: the whole point of the indeterminate tier is that it must NOT be
    # auto-penalized like a confirmed advanced-English requirement.
    job = _job(
        title="Data Analyst",
        description=(
            "Puesto 100% remoto. English required for occasional client calls."
            + "x" * 150
        ),
    )
    scored = ScoredJob(job=job, prefilter_score=50, prefilter_passed=True, ai_evaluated=True, ai_score=95)
    validated = validate(scored)
    assert validated.final_score == 95
    assert "english_required" not in validated.flags


def test_contradiction_strip_removes_seniority_and_self_cancelling_contras():
    contras = [
        "Puede estar sobrecalificado para el puesto.",
        "No maneja Power BI, pero sí tiene experiencia en Tableau.",
        "Requiere certificación en SAP que el candidato no tiene.",
    ]
    assert strip_contradictions(contras) == ["Requiere certificación en SAP que el candidato no tiene."]


def test_unevaluated_job_passes_through_validate_untouched():
    job = _job()
    scored = ScoredJob(job=job, prefilter_score=45, prefilter_passed=True)
    assert validate(scored) == scored


def test_validate_is_idempotent():
    job = _job(description="Puesto presencial en CDMX." + "x" * 200)
    scored = ScoredJob(job=job, prefilter_score=50, prefilter_passed=True, ai_evaluated=True, ai_score=90)
    once = validate(scored)
    twice = validate(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Ranking + end-to-end composition
# ---------------------------------------------------------------------------


def test_rank_scored_jobs_sorts_best_first():
    job1, job2 = _job(source_job_id="1"), _job(source_job_id="2")
    lower = ScoredJob(job=job1, prefilter_score=40, prefilter_passed=True, ai_evaluated=True, ai_score=60)
    higher = ScoredJob(job=job2, prefilter_score=90, prefilter_passed=True)
    assert rank_scored_jobs([lower, higher]) == [higher, lower]


def test_score_jobs_end_to_end_ranks_best_first_and_drops_rejects():
    criteria = _criteria(ai_cap_top_n=10)
    strong = _job(
        source_job_id="1",
        title="Business Intelligence Analyst",
        description="Puesto 100% remoto. Power BI SQL." + "x" * 200,
    )
    finance_intern = _job(
        source_job_id="2",
        title="Finance Intern",
        description="Accounts payable and budgeting support." + "x" * 200,
        remote_status=RemoteStatus.UNKNOWN,
    )
    router = _router({strong.signature: AiResult(signature=strong.signature, ai_score=88, pros=["Gran fit"])})

    result = score_jobs([strong, finance_intern], router, PROFILE, criteria)

    assert [item.job.signature for item in result] == [strong.signature]
    assert result[0].final_score == 88
