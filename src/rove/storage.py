"""JSON/JSONL read & write, in one place, with atomic full-file writes.

The legacy project had five different "load/save JSON" implementations
scattered around, and none were transactional: a process dying mid-write
left a corrupt file (see `legacy/jobmatch/storage.py`, which fixed this for
plain JSON only). Here that atomic pattern is kept for small pretty-JSON
files (`results.json`, `status.json`), and JSONL streaming is added for the
large per-source files (`raw/<source>.jsonl`, `gated.jsonl`,
`cache/signatures.jsonl`) so a crash never loses more than the last line and
big collections never have to sit fully in memory to be written.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import orjson


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read a JSON file. Returns `default` if missing, empty, or corrupt."""
    path = Path(path)
    if not path.exists():
        return default

    try:
        content = path.read_bytes()
    except OSError:
        return default

    if not content.strip():
        return default

    try:
        return orjson.loads(content)
    except orjson.JSONDecodeError:
        return default


def write_json(path: str | Path, data: Any) -> None:
    """Write JSON atomically (temp file in the same dir + `os.replace`)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_jsonl(path: str | Path) -> Iterator[Any]:
    """Stream-read a JSONL file, one decoded record per line.

    Corrupt trailing lines (e.g. from a crash mid-append) are skipped rather
    than failing the whole read.
    """
    path = Path(path)
    if not path.exists():
        return

    with path.open("rb") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                yield orjson.loads(line)
            except orjson.JSONDecodeError:
                continue


def append_jsonl(path: str | Path, record: Any) -> None:
    """Append one record as a single JSONL line. Used for streamed writes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as file:
        file.write(orjson.dumps(record))
        file.write(b"\n")


def write_jsonl(path: str | Path, records: Iterable[Any]) -> None:
    """Atomically overwrite a JSONL file from an in-memory iterable."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as file:
            for record in records:
                file.write(orjson.dumps(record))
                file.write(b"\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
