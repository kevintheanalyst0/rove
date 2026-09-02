"""Daily pre-run submit sweep (EATP-035, ADR-011 §5).

Sends every still-pending `draft_ready` application before the next day's
collection run fires — Kevin's own deadline: nothing he hasn't reviewed
should linger past the next run. Implemented as one daily sweep rather than
a per-job timer (simpler, and it structurally guarantees "resolved before
the next run" instead of relying on precise timestamp arithmetic).

Invoked by `rove-presubmit-sweep.service` (a systemd oneshot, not an HTTP
endpoint — this needs no run-lock or SSE progress, unlike the full pipeline
`/run`), scheduled shortly before `rove-daily-run.timer`'s 13:00 UTC trigger.
"""

from __future__ import annotations

from rove.apply import store as apply_store
from rove.apply.submit import submit_application
from rove.config import get_logger
from rove.inbox import store as inbox_store
from rove.profile import Profile, load_profile

logger = get_logger(__name__)


def sweep_pending_applications(profile: Profile | None = None) -> dict[str, str]:
    """Submits every `draft_ready` application, sequentially (never
    parallel — CLAUDE.md golden rule 2). Returns `{signature: resulting
    status}` for logging. Never raises: `submit_application` already
    catches its own failures into a `failed` entry, picked up again by the
    normal apply-prep pass on the run that follows this sweep."""
    profile = profile or load_profile()
    drafts = apply_store.draft_ready_entries()
    inbox = inbox_store.latest_entries()

    results: dict[str, str] = {}
    for signature, entry in drafts.items():
        inbox_entry = inbox.get(signature)
        if inbox_entry is None:
            logger.warning(
                "sweep: signature %s has a draft_ready entry but no matching inbox "
                "entry (already applied/dismissed by hand?) — skipping",
                signature,
            )
            continue
        updated = submit_application(inbox_entry.scored.job, profile, entry)
        results[signature] = updated.status.value
        logger.info(
            "sweep: %s (%s) -> %s", inbox_entry.scored.job.company, signature, updated.status.value
        )

    logger.info("sweep complete: %d draft(s) processed", len(results))
    return results


def main() -> None:
    sweep_pending_applications()


if __name__ == "__main__":
    main()
