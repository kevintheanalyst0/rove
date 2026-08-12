"""Une las 4 fuentes en un solo jobs.json, con deduplicación GLOBAL.

Antes (merge_jobs.py) solo concatenaba: una vacante presente en dos fuentes
entraba dos veces. Ahora se deduplica entre fuentes (por id exacto y por
similitud de título/empresa/descripción).
"""

from __future__ import annotations

from jobmatch import config
from jobmatch.console import console
from jobmatch.models import Job
from jobmatch.storage import read_json, write_json
from jobmatch.collectors.utils import is_duplicate

SOURCES = ["computrabajo", "occ", "indeed", "linkedin"]


def merge() -> list[Job]:
    console.header("Merge Jobs", "🔀")
    console.phase("Loading sources", "📂")

    all_jobs: list[Job] = []
    seen_ids: set[str] = set()
    duplicates = 0

    for source in SOURCES:
        raw = read_json(config.source_file(source), default=[])
        console.status(source, len(raw))

        for data in raw:
            job = Job.from_dict(data)

            if job.job_id in seen_ids:
                duplicates += 1
                continue
            if is_duplicate(job, all_jobs):
                duplicates += 1
                continue

            seen_ids.add(job.job_id)
            all_jobs.append(job)

    console.phase("Merging", "📦")
    console.status("Unique jobs", len(all_jobs))
    console.status("Duplicates removed", duplicates)

    console.phase("Saving results", "💾")
    write_json(config.JOBS_FILE, [job.to_dict() for job in all_jobs])
    console.success(str(config.JOBS_FILE))
    console.completed("Merge Jobs")

    return all_jobs


if __name__ == "__main__":
    merge()
