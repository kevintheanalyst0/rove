"""Standalone live test for the Indeed collector only — no AI, no other
sources, no web server (EATP-023, Kevin's ask: verifying a collector-level
fix — captcha detection, window behavior — shouldn't cost a ~10 min full
run + real AI quota every time).

Run via `Probar Indeed.bat`, or directly:
    .venv/bin/python scripts/test_indeed_live.py
"""

from __future__ import annotations

import time

from career_radar.collectors.indeed import IndeedCollector


def main() -> None:
    print("Corriendo el collector de Indeed (sin IA, sin las demás fuentes)...", flush=True)
    print("Si sale un captcha real de Cloudflare, la ventana de Chrome debería", flush=True)
    print("subirse sola al frente, maximizada.\n", flush=True)

    start = time.monotonic()
    jobs = list(IndeedCollector().collect())
    elapsed = time.monotonic() - start

    print(f"\nListo: {elapsed:.1f}s — {len(jobs)} vacantes encontradas.\n", flush=True)
    for job in jobs:
        print(f" - {job.title} | {job.company}", flush=True)


if __name__ == "__main__":
    main()
