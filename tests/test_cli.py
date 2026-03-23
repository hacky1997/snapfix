"""
Tests for snapfix.cli — the typer command-line interface.

Uses typer's CliRunner for isolated testing without spawning subprocesses.
"""
import pathlib

import pytest
from typer.testing import CliRunner

from snapfix.cli import app
from snapfix.store import SnapfixStore

runner = CliRunner()


def _populate(tmp_path: pathlib.Path) -> SnapfixStore:
    store = SnapfixStore(tmp_path)
    store.write("alpha", "@pytest.fixture\ndef alpha(): return {'a': 1}",
                {"scrubbed_fields": ["email"], "captured_at": "2026-03-01T12:00:00"})
    store.write("beta",  "@pytest.fixture\ndef beta(): return {'b': 2}",
                {"scrubbed_fields": [], "captured_at": "2026-03-01T13:00:00"})
    return store


def test_list_no_fixtures(tmp_path):
    result = runner.invoke(app, ["list", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No fixtures" in result.output


def test_list_shows_fixtures(tmp_path):
    _populate(tmp_path)
    result = runner.invoke(app, ["list", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta"  in result.output


def test_show_existing_fixture(tmp_path):
    _populate(tmp_path)
    result = runner.invoke(app, ["show", "alpha", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "@pytest.fixture" in result.output


def test_show_missing_fixture_exit_1(tmp_path):
    result = runner.invoke(app, ["show", "nonexistent", "--dir", str(tmp_path)])
    assert result.exit_code == 1


def test_clear_with_yes_flag(tmp_path):
    store = _populate(tmp_path)
    result = runner.invoke(app, ["clear", "alpha", "--dir", str(tmp_path), "--yes"])
    assert result.exit_code == 0
    assert not store.exists("alpha")
    assert store.exists("beta")


def test_clear_missing_fixture_exit_1(tmp_path):
    result = runner.invoke(app, ["clear", "ghost", "--dir", str(tmp_path), "--yes"])
    assert result.exit_code == 1


def test_clear_all_with_yes_flag(tmp_path):
    store = _populate(tmp_path)
    result = runner.invoke(app, ["clear-all", "--dir", str(tmp_path), "--yes"])
    assert result.exit_code == 0
    assert store.list() == []


def test_clear_all_empty_exits_0(tmp_path):
    result = runner.invoke(app, ["clear-all", "--dir", str(tmp_path), "--yes"])
    assert result.exit_code == 0
    assert "Nothing to clear" in result.output
