"""Match-quality report (EATP-017, P22): turns Kevin's labels into
`precision@shown` and a false-positive breakdown by reason, so a threshold
tune can be judged by evidence ("precision went from X to Y") instead of gut
feel. Kevin labels through the dashboard (`web/server.py`'s `/eval/*`
routes); this module only reads what he already recorded — it never labels
anything itself (CLAUDE.md §7: no live AI/ground-truth here, labels are
Kevin's).

Run as a script (`python -m career_radar.eval.report`) once Kevin has
labeled a run's worth of jobs. The first report ever computed has nothing to
compare against, so it's saved as the baseline automatically; `--set-baseline`
re-anchors the comparison point after a deliberate tuning change.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from career_radar import config
from career_radar.eval import labels as labels_store
from career_radar.eval.labels import Label, LabelEntry
from career_radar.storage import read_json, write_json


class EvalReport(BaseModel):
    generated_at: datetime
    total_labeled: int
    good: int
    bad: int
    precision: float | None = None  # good / total_labeled; None if nothing labeled yet
    fp_reasons: dict[str, int] = Field(default_factory=dict)


def compute_report(entries: Iterable[LabelEntry]) -> EvalReport:
    entries = list(entries)
    good = sum(1 for entry in entries if entry.label == Label.GOOD)
    bad = sum(1 for entry in entries if entry.label == Label.BAD)
    total = good + bad

    fp_reasons: dict[str, int] = {}
    for entry in entries:
        if entry.label == Label.BAD:
            reason = entry.reason.value if entry.reason else "unspecified"
            fp_reasons[reason] = fp_reasons.get(reason, 0) + 1

    return EvalReport(
        generated_at=datetime.now(UTC),
        total_labeled=total,
        good=good,
        bad=bad,
        precision=(good / total) if total else None,
        fp_reasons=fp_reasons,
    )


def save_baseline(report: EvalReport) -> None:
    write_json(config.EVAL_BASELINE_FILE, report.model_dump(mode="json"))


def load_baseline() -> EvalReport | None:
    raw = read_json(config.EVAL_BASELINE_FILE, default=None)
    if not raw:
        return None
    try:
        return EvalReport(**raw)
    except (TypeError, ValueError):
        return None


def generate_report(set_baseline: bool = False) -> tuple[EvalReport, EvalReport | None]:
    """Computes the current report from every label on disk. Returns
    `(report, baseline)` — `baseline` is `None` when there's nothing yet to
    compare against (first run ever, or `set_baseline` just reset it).

    A report with nothing labeled never becomes the baseline (`precision`
    would be `None`, a meaningless anchor) — it's returned as-is against
    whatever baseline already exists, so running this before Kevin has
    labeled anything can't silently lock in an empty baseline that blocks
    the first real one from being saved.
    """
    report = compute_report(labels_store.latest_labels().values())
    existing_baseline = load_baseline()

    if report.total_labeled == 0:
        return report, existing_baseline

    if set_baseline or existing_baseline is None:
        save_baseline(report)
        return report, None
    return report, existing_baseline


def format_report(report: EvalReport, baseline: EvalReport | None) -> str:
    if report.precision is None:
        return "Sin vacantes etiquetadas todavía — nada que reportar."

    lines = [f"Precisión@mostradas: {report.precision:.0%} ({report.good}/{report.total_labeled})"]
    if report.fp_reasons:
        lines.append("Falsos positivos por razón:")
        for reason, count in sorted(report.fp_reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {reason}: {count}")

    if baseline is not None and baseline.precision is not None:
        delta = report.precision - baseline.precision
        lines.append(f"Baseline: {baseline.precision:.0%} -> ahora {report.precision:.0%} (Δ {delta:+.0%})")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Career Radar — reporte de calidad de coincidencias")
    parser.add_argument(
        "--set-baseline",
        action="store_true",
        help="Guarda la corrida actual como nuevo baseline (usar después de un ajuste deliberado)",
    )
    args = parser.parse_args()

    report, baseline = generate_report(set_baseline=args.set_baseline)
    print(format_report(report, baseline))


if __name__ == "__main__":
    main()
