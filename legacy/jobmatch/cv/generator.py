"""Genera un CV adaptado a una vacante y lo devuelve como PDF."""

from __future__ import annotations

import os

from jobmatch import config
from jobmatch.cv.pdf import convert_docx_to_pdf
from jobmatch.cv.tailor import (
    apply_cv_strategy,
    detect_job_language,
    extract_skills,
    generate_cv_strategy,
    read_cv_docx,
)


def generate_cv(job: dict) -> str:
    job_description = job["job"]["description"]
    language = detect_job_language(job_description)

    if language == "en":
        source_cv = config.RESUME_DIR / "master_cv_en.docx"
        output_docx = config.OUTPUT_DIR / "Resume Kevin Castillo.docx"
        output_pdf = config.OUTPUT_DIR / "Resume Kevin Castillo.pdf"
    else:
        source_cv = config.RESUME_DIR / "master_cv_es.docx"
        output_docx = config.OUTPUT_DIR / "CV Kevin Castillo.docx"
        output_pdf = config.OUTPUT_DIR / "CV Kevin Castillo.pdf"

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    content = read_cv_docx(str(source_cv))
    skills = extract_skills(content)
    strategy = generate_cv_strategy(content, job_description, skills)
    apply_cv_strategy(str(source_cv), strategy, str(output_docx))
    convert_docx_to_pdf(str(output_docx), str(output_pdf))

    if os.path.exists(output_docx):
        os.remove(output_docx)

    return str(output_pdf)
