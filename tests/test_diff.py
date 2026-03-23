"""
Tests for snapfix.diff — structural snapshot diffing.
"""
import json
import pathlib
import tempfile

import pytest

from snapfix.diff import (
    _flatten,
    _serialized_lines,
    structural_diff,
    source_diff,
    SnapfixSnapshot,
)


# ── _flatten ──────────────────────────────────────────────────────────────────

def test_flatten_simple_dict():
    result = _flatten({"a": 1, "b": "x"})
    assert result == {"a": "1", "b": "'x'"}

def test_flatten_nested_dict():
    result = _flatten({"user": {"email": "x@y.com"}})
    assert "user.email" in result

def test_flatten_list():
    result = _flatten({"items": [1, 2, 3]})
    assert "items[0]" in result
    assert "items[2]" in result

def test_flatten_deeply_nested():
    d = {"a": {"b": {"c": {"d": "leaf"}}}}
    result = _flatten(d)
    assert "a.b.c.d" in result
    assert result["a.b.c.d"] == "'leaf'"

def test_flatten_empty():
    assert _flatten({}) == {}
    assert _flatten([]) == {}


# ── structural_diff ───────────────────────────────────────────────────────────

def test_diff_identical_returns_empty():
    d = {"a": 1, "b": "hello"}
    assert structural_diff(d, d, "test") == ""

def test_diff_added_field():
    old = {"a": 1}
    new = {"a": 1, "b": 2}
    diff = structural_diff(old, new, "test")
    assert "b:" in diff
    assert diff  # non-empty

def test_diff_removed_field():
    old = {"a": 1, "b": 2}
    new = {"a": 1}
    diff = structural_diff(old, new, "test")
    assert "b:" in diff

def test_diff_changed_value():
    old = {"status": "active"}
    new = {"status": "inactive"}
    diff = structural_diff(old, new, "test")
    assert "status:" in diff
    assert "'active'" in diff or "'inactive'" in diff

def test_diff_shows_plus_and_minus():
    old = {"x": 1}
    new = {"x": 2}
    diff = structural_diff(old, new, "test")
    lines = diff.splitlines()
    has_minus = any(l.startswith("-") and not l.startswith("---") for l in lines)
    has_plus  = any(l.startswith("+") and not l.startswith("+++") for l in lines)
    assert has_minus and has_plus

def test_diff_fromfile_tofile_labels():
    diff = structural_diff({"a": 1}, {"a": 2}, "my_fixture")
    assert "my_fixture (previous)" in diff
    assert "my_fixture (current)"  in diff

def test_diff_nested_change():
    old = {"user": {"plan": "free"}}
    new = {"user": {"plan": "pro"}}
    diff = structural_diff(old, new, "fixture")
    assert "user.plan" in diff

def test_diff_type_change_detected():
    old = {"amount": "'149.99'"}
    new = {"amount": 149.99}
    diff = structural_diff(old, new, "fixture")
    assert diff  # change detected


# ── source_diff ───────────────────────────────────────────────────────────────

def test_source_diff_identical():
    src = "def test(): return {}"
    assert source_diff(src, src, "f") == ""

def test_source_diff_changed():
    old = "def fixture():\n    return {'a': 1}"
    new = "def fixture():\n    return {'a': 2}"
    diff = source_diff(old, new, "fixture")
    assert diff
    assert "'a': 1" in diff or "'a': 2" in diff


# ── SnapfixSnapshot ───────────────────────────────────────────────────────────

def test_snapshot_save_and_load(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    data = {"user": {"plan": "pro"}, "amount": "149.99"}
    ss.save("invoice", data)
    loaded = ss.load("invoice")
    assert loaded == data

def test_snapshot_has_returns_true_after_save(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    assert not ss.has("invoice")
    ss.save("invoice", {"x": 1})
    assert ss.has("invoice")

def test_snapshot_delete(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    ss.save("invoice", {"x": 1})
    assert ss.delete("invoice")
    assert not ss.has("invoice")

def test_snapshot_delete_nonexistent_returns_false(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    assert not ss.delete("ghost")

def test_snapshot_list_names(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    ss.save("alpha", {"a": 1})
    ss.save("beta",  {"b": 2})
    names = ss.list_names()
    assert "alpha" in names
    assert "beta"  in names

def test_snapshot_rotation_creates_prev(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    ss.save("inv", {"version": 1})
    ss.save("inv", {"version": 2})
    # After second save, .prev.json should exist
    prev = ss._path("inv").with_suffix(".prev.json")
    assert prev.exists()
    prev_data = json.loads(prev.read_text())
    assert prev_data["version"] == 1

def test_snapshot_load_missing_raises(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    with pytest.raises(FileNotFoundError):
        ss.load("nonexistent")

def test_snapshot_atomic_write_no_tmp_leftover(tmp_path):
    ss = SnapfixSnapshot(tmp_path)
    ss.save("test", {"x": 1})
    assert not list(tmp_path.glob("**/*.tmp"))
