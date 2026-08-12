"""Filtros de calidad de vacantes.

Antes solo se aplicaban al colector de LinkedIn. Ahora son funciones
compartidas que TODOS los colectores usan, de modo que las cuatro fuentes
descartan lo mismo. Las listas de inglés (que antes estaban duplicadas
entre substring y regex) están consolidadas aquí.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Empresas excluidas
# ---------------------------------------------------------------------------
EXCLUDED_COMPANIES = {
    "bairesdev",
    "indi staffing services",
}

# ---------------------------------------------------------------------------
# Títulos excluidos (roles fuera del objetivo). Deduplicado.
# ---------------------------------------------------------------------------
EXCLUDED_TITLE_KEYWORDS = {
    # Ventas
    "account executive", "inside sales", "sales executive", "sales representative",
    # Marketing
    "marketing", "seo", "social media", "media buyer", "content creator",
    "copywriter", "strategist", "media manager", "paid media", "youtube",
    "streaming", "video manager", "video editor",
    # Reclutamiento / RH
    "recruiter", "talent acquisition", "human resources", "hr ", "people operations",
    # Soporte / Call center
    "customer service", "customer support", "call center",
    # Finanzas / Contabilidad
    "bookkeeper", "accounting",
    # Legal
    "legal", "attorney", "lawyer", "paralegal",
    # Salud
    "nurse", "doctor", "physician", "clinical", "mental health", "care coordinator",
    # Educación
    "teacher", "tutor",
    # Administración / Operaciones
    "coordinator", "assistant",
    # Otros
    "government", "public sector",
}

# Palabras que "rescatan" un título ambiguo (p. ej. "manager" solo se excluye
# si NO contiene ninguna de estas palabras relacionadas con datos/BI).
CONDITIONAL_TITLE_RULES = {
    "manager": {"data", "analytics", "business", "bi", "power bi", "sql", "machine learning", "ai"},
    "specialist": {"data", "analytics", "business", "analyst", "bi", "power bi", "sql", "automation", "report"},
    "support": {"analyst", "data", "business", "bi", "sql"},
    "planner": {"data", "analytics", "business", "bi"},
    "coordinator": {"data", "analytics", "business"},
    "operations": {"data", "analytics", "business", "bi"},
}

# ---------------------------------------------------------------------------
# Inglés avanzado obligatorio (motivo de descarte). Consolidado.
# ---------------------------------------------------------------------------
# Frases claras (coincidencia por substring).
_ENGLISH_PHRASES = [
    "advanced english", "advanced level of english", "advanced spoken english",
    "advanced written english", "excellent english", "strong english",
    "fluent english", "fluency in english", "english fluency", "native english",
    "professional english", "english required", "english is required",
    "must speak english", "written and spoken english", "resume in english",
    "cv in english", "interview in english", "bilingual", "fully bilingual",
    "english communication skills", "strong communication skills in english",
    # Español
    "inglés avanzado", "ingles avanzado", "inglés fluido", "ingles fluido",
    "dominio del inglés", "dominio del ingles", "inglés indispensable",
    "ingles indispensable",
]

# Tokens cortos sensibles a límites de palabra (evita falsos positivos como
# "abc1"): se comprueban con \b para no coincidir dentro de otras palabras.
_ENGLISH_REGEX = [
    r"\bc1\b", r"\bc2\b", r"\bc1 english\b", r"\bc2 english\b",
    r"\benglish level c1\b", r"\benglish level c2\b",
    r"\bnivel c1\b", r"\bnivel c2\b", r"\bielts\b", r"\btoefl\b",
]


def is_excluded_company(company: str) -> bool:
    if not company:
        return False
    company = company.lower().strip()
    return any(blocked in company for blocked in EXCLUDED_COMPANIES)


def has_excluded_title(title: str) -> bool:
    if not title:
        return False
    title = title.lower()
    return any(keyword in title for keyword in EXCLUDED_TITLE_KEYWORDS)


def fails_conditional_title_rules(title: str) -> bool:
    if not title:
        return False
    title = title.lower()
    for trigger, required_words in CONDITIONAL_TITLE_RULES.items():
        if trigger not in title:
            continue
        return not any(word in title for word in required_words)
    return False


def requires_advanced_english(title: str, description: str) -> bool:
    text = f"{title}\n{description}".lower()
    if any(phrase in text for phrase in _ENGLISH_PHRASES):
        return True
    return any(re.search(pattern, text) for pattern in _ENGLISH_REGEX)


def title_is_rejected(title: str, company: str) -> bool:
    """Filtros que solo necesitan título y empresa (sin descripción).

    Se pueden aplicar ANTES de pedir el detalle de una vacante, ahorrando
    peticiones (menos tiempo y menos riesgo de 429)."""
    return (
        is_excluded_company(company)
        or has_excluded_title(title)
        or fails_conditional_title_rules(title)
    )
