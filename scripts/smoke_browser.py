"""Live smoke test for the browser layer — no network, no scraping.

Opens a real Chrome through the same `build_page` the collectors use, loads
`about:blank`, and shuts it down through `close_page`. Exists because
EATP-025's whole failure mode (a browser that dies, then a teardown call
that blocks forever waiting on it) is invisible to the mocked unit tests:
they never launch a process at all.

Run it after any change to the browser layer, or on a new machine, to
confirm launch + teardown actually work there:

    .venv\\Scripts\\python.exe scripts\\smoke_browser.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from career_radar.collectors import browser  # noqa: E402


def main() -> int:
    print(f"chrome binary : {browser.resolve_chrome_path()}")

    started = time.monotonic()
    page = browser.build_page(use_profile=True, start_minimized=True)
    print(f"launched      : {time.monotonic() - started:.1f}s  (pid {page.process_id})")

    page.get("about:blank")
    print(f"navigated     : {page.url}")

    pid = page.process_id
    closing = time.monotonic()
    browser.close_page(page)
    elapsed = time.monotonic() - closing
    print(f"closed        : {elapsed:.1f}s")

    # The point of the exercise: teardown must not hang, and must actually
    # leave no browser behind to eat memory on the next source.
    if elapsed > 25:
        print("FAIL: close_page took longer than its own ceiling")
        return 1
    try:
        import os

        os.kill(pid, 0)
    except OSError:
        print("OK: browser process is gone")
        return 0
    print(f"FAIL: pid {pid} still alive after close_page")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
