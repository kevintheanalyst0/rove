"""Orquestación del análisis con IA.

Flujo: matcher -> seleccionar las mejores -> lotes en PARALELO a Gemini -> guardar.

Los lotes se envían todos a la vez (dentro del límite de RPM configurado).
En lugar de esperar 60s × N lotes de forma secuencial, se espera una sola
ronda de ~60-90s mientras Gemini procesa todos en paralelo.
"""

from __future__ import annotations

import threading

from jobmatch import config
from jobmatch.console import console
from jobmatch.models import AnalyzedJob, Job
from jobmatch.profile import PROFILE
from jobmatch.storage import read_json, write_json
from jobmatch.pipeline import ai, matcher, state


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _analyzed_dict(item: dict, gemini: dict) -> dict:
    job = item["job"]
    score = gemini["gemini_score"]
    return AnalyzedJob(
        job_id=job.get("job_id", ""),
        title=job.get("title", ""),
        company=job.get("company", ""),
        url=item["url"],
        matcher_score=item["matcher_score"],
        ai_analyzed=True,
        gemini_score=score,
        final_score=score,
        summary=gemini["summary"],
        pros=gemini["pros"],
        contras=gemini["contras"],
        job=job,
    ).to_dict()


def _unanalyzed_dict(item: dict) -> dict:
    job = item["job"]
    return AnalyzedJob(
        job_id=job.get("job_id", ""),
        title=job.get("title", ""),
        company=job.get("company", ""),
        url=item["url"],
        matcher_score=item["matcher_score"],
        ai_analyzed=False,
        gemini_score=None,
        final_score=item["matcher_score"],
        summary="",
        pros=[],
        contras=[],
        job=job,
    ).to_dict()


def _pause(message: str, analyzed: list, processed_jobs: list) -> None:
    state.save_analyzed_jobs(analyzed)
    state.save_batches(processed_jobs)
    state.set_status("Paused", message, jobs_processed=len(processed_jobs))
    console.phase("Saving progress", "💾")
    console.warning(message)


def process_jobs() -> list | None:
    console.header("Processing Jobs", "⚙")
    console.phase("Loading data", "📂")

    status = state.load_status()
    if status.get("status") != "Paused":
        state.clear_batches()

    state.set_status("Running", "Analysis in progress...")

    raw_jobs = read_json(config.JOBS_FILE, default=[])
    console.status("jobs.json", len(raw_jobs))

    analyzed = state.load_analyzed_jobs()
    analyzed_lookup = {a["job_id"]: a for a in analyzed if a.get("job_id")}

    if state.batches_exist():
        processed_jobs = state.load_batches().get("processed_jobs", [])
        console.status("Resuming session", f"{len(processed_jobs)} jobs")
    else:
        processed_jobs = []
    processed_ids = {p.get("job_id") for p in processed_jobs if p.get("job_id")}

    # --- Matcher ---
    console.phase("Matcher scores", "🎯")
    jobs_to_analyze: list[dict] = []
    total = len(raw_jobs)
    for index, raw in enumerate(raw_jobs, start=1):
        job_id = raw.get("job_id", "")
        if job_id not in analyzed_lookup and job_id not in processed_ids:
            result = matcher.calculate_match(Job.from_dict(raw))
            jobs_to_analyze.append(
                {"job": raw, "url": raw.get("url", ""), "matcher_score": result["score"]}
            )
        console.progress(index, total)

    jobs_to_analyze.sort(key=lambda e: e["matcher_score"], reverse=True)
    top_jobs = jobs_to_analyze[: config.AI_TOP_JOBS]
    remaining_jobs = jobs_to_analyze[config.AI_TOP_JOBS:]
    batches = _chunk(top_jobs, config.AI_BATCH_SIZE)

    console.phase("AI analysis (parallel)", "🤖")
    console.status("Jobs selected", len(top_jobs))
    console.status("Batches", len(batches))
    console.status("Parallel workers", min(len(batches), config.AI_REQUESTS_PER_MINUTE))
    console.blank()

    # Contador de progreso compartido entre hilos
    done_lock = threading.Lock()
    done_count = [0]

    def on_batch_done(batch_index: int, n_results: int) -> None:
        with done_lock:
            done_count[0] += 1
            console.progress(done_count[0], len(batches), "Gemini batches")

    # --- Envío paralelo ---
    raw_results, quota_hit = ai.analyze_all_batches(batches, PROFILE, on_batch_done)

    if quota_hit and not raw_results:
        # Ningún lote completó → pausar todo.
        _pause(
            "Pipeline en pausa: cuota de Gemini agotada. Se reanudará al re-ejecutar.",
            analyzed,
            processed_jobs,
        )
        return None

    if quota_hit:
        console.warning("Cuota de Gemini alcanzada: algunos lotes no se procesaron.")

    # --- Consolidar resultados ---
    # Ordenar por batch_index para que el emparejamiento VACANTE_N sea correcto.
    raw_results.sort(key=lambda x: x[0])

    completed_batch_indices = {idx for idx, _ in raw_results}

    for batch_index, batch in enumerate(batches):
        if batch_index not in completed_batch_indices:
            # Este lote no llegó a Gemini (cuota a mitad); lo dejamos sin analizar.
            for item in batch:
                processed_jobs.append(_unanalyzed_dict(item))
            continue

        gemini_results = next(r for i, r in raw_results if i == batch_index)
        lookup = {r["job_id"]: r for r in gemini_results}

        for position, item in enumerate(batch, start=1):
            gemini = lookup.get(f"VACANTE_{position}")
            if gemini:
                record = _analyzed_dict(item, gemini)
                processed_jobs.append(record)
                analyzed.append(record)
            else:
                processed_jobs.append(_unanalyzed_dict(item))

    state.save_analyzed_jobs(analyzed)

    for item in remaining_jobs:
        processed_jobs.append(_unanalyzed_dict(item))

    processed_jobs.sort(key=lambda e: e["final_score"], reverse=True)
    state.set_status("Success", "Analysis completed.", jobs_processed=len(processed_jobs))

    console.phase("Saving results", "💾")
    write_json(config.LATEST_JOBS_FILE, processed_jobs)
    console.success(str(config.LATEST_JOBS_FILE))

    state.clear_batches()
    console.completed("Processing Jobs")
    return processed_jobs


if __name__ == "__main__":
    process_jobs()
