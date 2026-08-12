from __future__ import annotations

import pytest

from career_radar import storage

# ---------------------------------------------------------------------------
# read_json / write_json
# ---------------------------------------------------------------------------


def test_read_json_missing_file_returns_default(tmp_path):
    assert storage.read_json(tmp_path / "nope.json", default="fallback") == "fallback"


def test_read_json_empty_file_returns_default(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("")
    assert storage.read_json(path, default={}) == {}


def test_read_json_corrupt_file_returns_default(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json")
    assert storage.read_json(path, default=None) is None


def test_write_json_then_read_json_roundtrips(tmp_path):
    path = tmp_path / "sub" / "data.json"
    payload = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
    storage.write_json(path, payload)
    assert storage.read_json(path) == payload


def test_write_json_leaves_no_temp_file_behind(tmp_path):
    path = tmp_path / "data.json"
    storage.write_json(path, {"a": 1})
    leftovers = [p for p in tmp_path.iterdir() if p.name != "data.json"]
    assert leftovers == []


def test_write_json_is_atomic_existing_file_survives_a_failed_write(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    storage.write_json(path, {"version": 1})

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(storage.orjson, "dumps", boom)
    with pytest.raises(RuntimeError):
        storage.write_json(path, {"version": 2})

    # Original file untouched; no stray temp file left around.
    assert storage.read_json(path) == {"version": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]


# ---------------------------------------------------------------------------
# JSONL: append / stream-read / atomic overwrite
# ---------------------------------------------------------------------------


def test_read_jsonl_missing_file_yields_nothing(tmp_path):
    assert list(storage.read_jsonl(tmp_path / "nope.jsonl")) == []


def test_append_jsonl_then_read_jsonl_roundtrips(tmp_path):
    path = tmp_path / "raw.jsonl"
    storage.append_jsonl(path, {"i": 1})
    storage.append_jsonl(path, {"i": 2})
    storage.append_jsonl(path, {"i": 3})
    assert list(storage.read_jsonl(path)) == [{"i": 1}, {"i": 2}, {"i": 3}]


def test_read_jsonl_skips_corrupt_trailing_line(tmp_path):
    path = tmp_path / "raw.jsonl"
    storage.append_jsonl(path, {"i": 1})
    with path.open("ab") as f:
        f.write(b"{not json, crash mid-write")  # no trailing newline
    assert list(storage.read_jsonl(path)) == [{"i": 1}]


def test_write_jsonl_atomically_overwrites(tmp_path):
    path = tmp_path / "raw.jsonl"
    storage.append_jsonl(path, {"i": "stale"})
    storage.write_jsonl(path, [{"i": 1}, {"i": 2}])
    assert list(storage.read_jsonl(path)) == [{"i": 1}, {"i": 2}]


def test_write_jsonl_leaves_no_temp_file_behind(tmp_path):
    path = tmp_path / "raw.jsonl"
    storage.write_jsonl(path, [{"i": 1}])
    leftovers = [p for p in tmp_path.iterdir() if p.name != "raw.jsonl"]
    assert leftovers == []
