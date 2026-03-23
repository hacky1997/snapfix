"""
Tests for snapfix.store — atomic fixture file I/O and index management.
"""
import pathlib

import pytest

from snapfix.store import SnapfixStore


def test_write_creates_file(tmp_path):
    store = SnapfixStore(tmp_path)
    p = store.write("my_fix", "# content", {})
    assert p.exists()
    assert p.read_text() == "# content"

def test_write_creates_index(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("my_fix", "# content", {"ts": "2026"})
    assert (tmp_path / ".snapfix_index.json").exists()

def test_list_returns_entries(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("a", "# a", {})
    store.write("b", "# b", {})
    entries = store.list()
    assert len(entries) == 2

def test_exists_true(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("my_fix", "# content", {})
    assert store.exists("my_fix")

def test_exists_false(tmp_path):
    store = SnapfixStore(tmp_path)
    assert not store.exists("nonexistent")

def test_delete_removes_file(tmp_path):
    store = SnapfixStore(tmp_path)
    p = store.write("to_delete", "# content", {})
    assert p.exists()
    store.delete("to_delete")
    assert not p.exists()

def test_delete_removes_from_index(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("to_delete", "# content", {})
    store.delete("to_delete")
    assert not store.exists("to_delete")

def test_delete_nonexistent_returns_false(tmp_path):
    store = SnapfixStore(tmp_path)
    assert store.delete("does_not_exist") is False

def test_write_is_atomic_no_tmp_leftover(tmp_path):
    """After a write, no .tmp file should remain."""
    store = SnapfixStore(tmp_path)
    store.write("atomic", "content", {})
    assert not list(tmp_path.glob("*.tmp"))

def test_overwrite_replaces_content(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("fix", "# v1", {})
    store.write("fix", "# v2", {})
    p = pathlib.Path(store._load_index()["fix"]["path"])
    assert p.read_text() == "# v2"

def test_corrupted_index_recovers(tmp_path):
    """If the index file is corrupt, store should recover gracefully."""
    store = SnapfixStore(tmp_path)
    (tmp_path / ".snapfix_index.json").write_text("NOT VALID JSON")
    entries = store.list()
    assert entries == []

def test_fixture_filename_uses_safe_name(tmp_path):
    store = SnapfixStore(tmp_path)
    p = store.write("my-bad.name!", "# content", {})
    assert " " not in p.name
    assert "!" not in p.name
