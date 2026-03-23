"""
Tests for snapfix.verify — fixture health checker.
"""
import pathlib
import pytest
from snapfix.verify import verify_file, verify_directory, format_verify_report


def _write(tmp_path: pathlib.Path, name: str, content: str) -> pathlib.Path:
    p = tmp_path / f"snapfix_{name}.py"
    p.write_text(content)
    return p


_VALID = """
import pytest
from snapfix import reconstruct

@pytest.fixture
def {name}():
    return reconstruct({{'id': 'INV-001', 'plan': 'pro', 'amount': {{'__snapfix_type__': 'decimal', 'value': '9.99'}}}})
"""

_NONE_RETURN = """
import pytest
from snapfix import reconstruct

@pytest.fixture
def {name}():
    return reconstruct(None)
"""

_SYNTAX_ERROR = """
import pytest
def {name}(
    # syntax error — missing closing paren
"""

_IMPORT_ERROR = """
import pytest
from nonexistent_package_xyz import something

@pytest.fixture
def {name}():
    return {{'x': 1}}
"""

_WITH_TRUNCATED = """
import pytest
from snapfix import reconstruct

@pytest.fixture
def {name}():
    return reconstruct({{'data': {{'__snapfix_truncated__': True, '__snapfix_size__': 999999}}}})
"""


# ── verify_file: passing cases ────────────────────────────────────────────────

def test_valid_fixture_passes(tmp_path):
    f = _write(tmp_path, "invoice", _VALID.format(name="invoice"))
    r = verify_file(f)
    assert r.passed
    assert r.error is None


def test_none_return_passes_with_warning(tmp_path):
    f = _write(tmp_path, "null_resp", _NONE_RETURN.format(name="null_resp"))
    r = verify_file(f)
    assert r.passed
    assert any("None" in w for w in r.warnings)


# ── verify_file: failing cases ────────────────────────────────────────────────

def test_syntax_error_fails(tmp_path):
    f = _write(tmp_path, "broken", _SYNTAX_ERROR.format(name="broken"))
    r = verify_file(f)
    assert not r.passed
    assert "SyntaxError" in r.error


def test_import_error_fails(tmp_path):
    f = _write(tmp_path, "bad_import", _IMPORT_ERROR.format(name="bad_import"))
    r = verify_file(f)
    assert not r.passed
    assert r.error is not None


def test_missing_fixture_function_fails(tmp_path):
    f = _write(tmp_path, "no_fn", "# empty file\n")
    r = verify_file(f)
    assert not r.passed


# ── verify_file: strict mode ──────────────────────────────────────────────────

def test_truncated_passes_in_normal_mode(tmp_path):
    f = _write(tmp_path, "trunc", _WITH_TRUNCATED.format(name="trunc"))
    r = verify_file(f, strict=False)
    assert r.passed
    assert any("truncated" in w for w in r.warnings)


def test_truncated_fails_in_strict_mode(tmp_path):
    f = _write(tmp_path, "trunc_strict", _WITH_TRUNCATED.format(name="trunc_strict"))
    r = verify_file(f, strict=True)
    assert not r.passed
    assert r.error is not None


# ── verify_directory ──────────────────────────────────────────────────────────

def test_verify_directory_all_pass(tmp_path):
    for name in ["a", "b", "c"]:
        _write(tmp_path, name, _VALID.format(name=name))
    results = verify_directory(tmp_path)
    assert len(results) == 3
    assert all(r.passed for r in results)


def test_verify_directory_mixed(tmp_path):
    _write(tmp_path, "good",   _VALID.format(name="good"))
    _write(tmp_path, "broken", _SYNTAX_ERROR.format(name="broken"))
    results = verify_directory(tmp_path)
    assert len(results) == 2
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    assert len(passed) == 1
    assert len(failed) == 1


def test_verify_directory_empty(tmp_path):
    results = verify_directory(tmp_path)
    assert results == []


# ── format_verify_report ──────────────────────────────────────────────────────

def test_format_report_all_pass(tmp_path):
    _write(tmp_path, "ok", _VALID.format(name="ok"))
    results = verify_directory(tmp_path)
    report = format_verify_report(results, tmp_path)
    assert "ALL VALID" in report or "Passed" in report


def test_format_report_failures(tmp_path):
    _write(tmp_path, "bad", _SYNTAX_ERROR.format(name="bad"))
    results = verify_directory(tmp_path)
    report = format_verify_report(results, tmp_path)
    assert "FAILED" in report or "Failed" in report


def test_format_report_shows_counts(tmp_path):
    _write(tmp_path, "x", _VALID.format(name="x"))
    results = verify_directory(tmp_path)
    report = format_verify_report(results, tmp_path)
    assert "1" in report
