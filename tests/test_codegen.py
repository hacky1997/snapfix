"""
Tests for snapfix.codegen — the @pytest.fixture source code generator.
"""
import ast
import datetime

import pytest

from snapfix.codegen import SnapfixCodegen, _sanitize

CG  = SnapfixCodegen()
NOW = datetime.datetime(2026, 3, 1, 12, 0, 0)


def test_generated_file_is_valid_python():
    src = CG.generate("my_fixture", {"x": 1}, [], NOW)
    ast.parse(src)  # raises SyntaxError if invalid

def test_generated_fixture_has_decorator():
    src = CG.generate("my_fixture", {"x": 1}, [], NOW)
    assert "@pytest.fixture" in src

def test_generated_fixture_imports_reconstruct():
    src = CG.generate("my_fixture", {"x": 1}, [], NOW)
    assert "from snapfix import reconstruct" in src

def test_generated_file_has_timestamp_comment():
    src = CG.generate("my_fixture", {}, [], datetime.datetime(2026, 3, 1))
    assert "2026" in src

def test_generated_file_has_scrub_comment():
    src = CG.generate("f", {}, ["email", "token"], NOW)
    assert "email" in src
    assert "token" in src

def test_generated_file_no_scrub_says_none():
    src = CG.generate("f", {}, [], NOW)
    assert "none" in src.lower()

def test_generated_function_name_is_valid_identifier():
    src = CG.generate("my_fixture", {}, [], NOW)
    tree = ast.parse(src)
    fn_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert all(name.isidentifier() for name in fn_names)

def test_name_with_special_chars_is_sanitized():
    src = CG.generate("my-bad.name!2", {}, [], NOW)
    ast.parse(src)  # must not raise

def test_nested_dict_is_valid_python():
    data = {"a": {"b": [1, None, True]}, "ts": "2026-01-01T00:00:00"}
    src  = CG.generate("nested", data, [], NOW)
    ast.parse(src)

def test_empty_dict_is_valid_python():
    src = CG.generate("empty", {}, [], NOW)
    ast.parse(src)

def test_none_value_is_valid_python():
    src = CG.generate("nullable", {"val": None}, [], NOW)
    ast.parse(src)
    assert "None" in src


# ── _sanitize helper ──────────────────────────────────────────────────────────

def test_sanitize_replaces_hyphens():
    assert "-" not in _sanitize("my-name")

def test_sanitize_replaces_dots():
    assert "." not in _sanitize("my.name")

def test_sanitize_prefixes_digit_start():
    result = _sanitize("2bad")
    assert result[0] == "_"

def test_sanitize_empty_string():
    assert _sanitize("") == "_unnamed"

def test_sanitize_already_valid():
    assert _sanitize("good_name") == "good_name"
