from __future__ import annotations

from career_radar.criteria import (
    classify_remote,
    classify_remote_with_evidence,
    has_excluded_title,
    is_excluded_company,
    load_criteria,
    requires_advanced_english,
    title_caution_flags,
    title_is_rejected,
)
from career_radar.models import RemoteStatus
from career_radar.profile import load_profile

# ---------------------------------------------------------------------------
# Loaders validate
# ---------------------------------------------------------------------------


def test_load_profile_validates():
    profile = load_profile()
    assert profile.name == "Kevin Castillo"
    assert profile.english_level == "B2"
    assert "Data Analyst" in profile.target_roles
    assert profile.priority.overqualification_is_positive is True
    assert profile.priority.seniority_is_priority is False


def test_load_criteria_validates():
    criteria = load_criteria()
    assert "bairesdev" in criteria.excluded_companies
    assert criteria.matcher.score_floors.prefilter_reject_floor > 0
    assert criteria.remote_signals.max_onsite_days_per_month == 1


def test_loaders_are_cached_singletons():
    assert load_profile() is load_profile()
    assert load_criteria() is load_criteria()


# ---------------------------------------------------------------------------
# Excluded company / blanket title exclusions
# ---------------------------------------------------------------------------


def test_excluded_company_matches_case_insensitively():
    assert is_excluded_company("BairesDev")
    assert not is_excluded_company("Acme Corp")


def test_blanket_excluded_titles():
    for title in [
        "Senior Recruiter",
        "SEO Marketing Specialist",
        "Customer Support Agent",
        "Bookkeeper",
        "Graphic Designer",
        "DevOps Engineer",  # "devops" is blanket even without "engineer" rescue check
    ]:
        assert has_excluded_title(title), title


# ---------------------------------------------------------------------------
# Title caution words — ADVISORY ONLY, never a hard reject (Kevin's "Analista
# administrativo" case: the description must always get read first).
# ---------------------------------------------------------------------------


def test_ambiguous_titles_with_rescue_word_have_no_caution_flags():
    for title in [
        "Power BI Developer",
        "Data Engineer",
        "Business Systems Administrator",
        "BI Reporting Engineer",
        "Analytics Specialist",
    ]:
        assert title_caution_flags(title) == [], title


def test_ambiguous_titles_without_rescue_word_are_flagged_not_rejected():
    for title in [
        "Backend Developer",
        "Network Engineer",
        "System Administrator",
        "Security Analyst",
        "Financial Analyst",
        "Operations Manager",
    ]:
        assert title_caution_flags(title), title  # flagged for the matcher/AI...
        assert not title_is_rejected(title, "Acme")  # ...but never hard-rejected on title alone


def test_plain_title_never_hard_rejects_on_ambiguity_alone():
    # The concrete case Kevin hit in the legacy system: a plain, unremarkable
    # title must still reach the description-reading stages.
    assert not title_is_rejected("Analista administrativo", "Acme")


def test_title_is_rejected_only_covers_absolute_categories():
    assert title_is_rejected("Graphic Designer", "Acme")
    assert title_is_rejected("Data Analyst", "BairesDev")
    assert not title_is_rejected("Power BI Developer", "Acme")
    assert not title_is_rejected("Analista de Datos", "Acme")


# ---------------------------------------------------------------------------
# Advanced English
# ---------------------------------------------------------------------------


def test_advanced_english_phrase_flags_true():
    assert requires_advanced_english("Data Analyst", "Se requiere inglés avanzado")


def test_advanced_english_regex_flags_true():
    assert requires_advanced_english("Data Analyst", "English level C1 required")
    assert requires_advanced_english("Data Analyst", "Se requiere TOEFL")


def test_intermediate_english_does_not_flag():
    assert not requires_advanced_english("Data Analyst", "Inglés intermedio deseable, no excluyente")


# ---------------------------------------------------------------------------
# Remote classification (ADR-002)
# ---------------------------------------------------------------------------


def test_classify_remote_positive_signal():
    assert classify_remote("Puesto 100% remoto, trabaja desde donde quieras") == RemoteStatus.REMOTE


def test_classify_remote_hybrid_phrase_overrides_positive():
    assert classify_remote("Remoto, modelo híbrido con 2 días en oficina") == RemoteStatus.HYBRID


def test_classify_remote_onsite_phrase():
    assert classify_remote("Puesto presencial en CDMX") == RemoteStatus.ONSITE


def test_classify_remote_weekly_onsite_is_hybrid():
    assert classify_remote("Trabajo remoto, 2 dias a la semana en oficina") == RemoteStatus.HYBRID


def test_classify_remote_within_monthly_tolerance_is_remote():
    assert classify_remote("Trabajo remoto, 1 dia al mes en oficina") == RemoteStatus.REMOTE


def test_classify_remote_beyond_monthly_tolerance_is_hybrid():
    assert classify_remote("Trabajo remoto, 3 dias al mes en oficina") == RemoteStatus.HYBRID


def test_classify_remote_no_signal_is_unknown():
    assert classify_remote("Analista de datos con experiencia en SQL") == RemoteStatus.UNKNOWN


def test_classify_remote_empty_text_is_unknown():
    assert classify_remote("") == RemoteStatus.UNKNOWN


# ---------------------------------------------------------------------------
# Remote evidence — the phrase(s) that decided the classification (auditable)
# ---------------------------------------------------------------------------


def test_remote_evidence_captures_the_deciding_positive_phrase():
    status, evidence = classify_remote_with_evidence("Puesto 100% remoto para todo el pais")
    assert status == RemoteStatus.REMOTE
    assert evidence and all(phrase in "puesto 100% remoto para todo el pais" for phrase in evidence)


def test_remote_evidence_captures_the_deciding_hybrid_phrase_even_with_remote_present():
    status, evidence = classify_remote_with_evidence("Remoto, modelo híbrido con 2 días en oficina")
    assert status == RemoteStatus.HYBRID
    assert evidence


def test_remote_evidence_is_empty_when_there_is_no_signal_at_all():
    status, evidence = classify_remote_with_evidence("Analista de datos con experiencia en SQL")
    assert status == RemoteStatus.UNKNOWN
    assert evidence == []


def test_remote_evidence_within_monthly_tolerance_keeps_both_matches():
    # Auditable: shows the office-visit mention AND what confirmed it as
    # remote anyway, rather than hiding the "hasta 1 día al mes" nuance.
    status, evidence = classify_remote_with_evidence("Trabajo remoto, 1 dia al mes en oficina")
    assert status == RemoteStatus.REMOTE
    assert len(evidence) == 2
