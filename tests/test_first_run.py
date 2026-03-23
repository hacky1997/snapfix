"""
Tests for the first-run experience — loud errors, colored output,
inline type comments in generated fixtures.
"""
import ast
import datetime
import decimal
import os
import pathlib
import sys
import warnings

import pytest


def _reload():
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]


# ── Colored terminal output helpers ──────────────────────────────────────────

def test_color_helpers():
    from snapfix.capture import _c, _supports_color
    # _c should always return the text even without a tty
    result = _c("hello", "32")
    assert "hello" in result

def test_success_message_printed_to_stderr(tmp_path, capsys):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("success_msg_test")
    def fn():
        return {"status": "ok"}

    fn()
    captured = capsys.readouterr()
    assert "snapfix" in captured.err
    assert "fixture written" in captured.err

def test_scrubbed_fields_shown_in_success_message(tmp_path, capsys):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("scrub_msg_test")
    def fn():
        return {"email": "x@y.com", "plan": "pro"}

    fn()
    captured = capsys.readouterr()
    # Should mention 'email' in the scrubbed line
    assert "email" in captured.err

def test_failure_message_is_loud(tmp_path, capsys):
    """When capture fails, the error must be visible — not a silent warning."""
    os.environ["SNAPFIX_OUTPUT_DIR"] = "/this/path/does/not/exist/at/all"
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("failure_msg_test")
    def fn():
        return {"x": 1}

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        fn()  # should not raise

    captured = capsys.readouterr()
    assert "FAILED" in captured.err or "✗" in captured.err

def test_failure_does_not_raise(tmp_path):
    """Capture failure must NEVER raise — only warn."""
    os.environ["SNAPFIX_OUTPUT_DIR"] = "/nonexistent/path"
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("no_raise_test")
    def fn():
        return {"x": 1}

    # Must not raise despite bad output dir
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = fn()
    assert result == {"x": 1}

def test_failure_hint_for_permission_error(tmp_path, capsys, monkeypatch):
    """A permission error should trigger a specific hint."""
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()

    from snapfix import capture
    from snapfix import store as store_mod

    original_write = store_mod.SnapfixStore.write

    def failing_write(*a, **kw):
        raise PermissionError("Permission denied: /some/path")

    monkeypatch.setattr(store_mod.SnapfixStore, "write", failing_write)

    @capture("hint_test")
    def fn():
        return {"x": 1}

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        fn()

    captured = capsys.readouterr()
    assert "permission" in captured.err.lower() or "SNAPFIX_OUTPUT_DIR" in captured.err


# ── Inline type comments in generated fixtures ────────────────────────────────

def test_datetime_has_inline_comment(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("datetime_comment_test")
    def fn():
        return {"ts": datetime.datetime(2026, 3, 1, 12, 0, 0)}

    fn()
    src = list(tmp_path.glob("snapfix_*.py"))[0].read_text()
    assert "# datetime" in src

def test_decimal_has_inline_comment(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("decimal_comment_test")
    def fn():
        return {"amount": decimal.Decimal("149.99")}

    fn()
    src = list(tmp_path.glob("snapfix_*.py"))[0].read_text()
    assert "# Decimal" in src

def test_source_function_in_header(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("source_ref_test")
    def my_service_function():
        return {"ok": True}

    my_service_function()
    src = list(tmp_path.glob("snapfix_*.py"))[0].read_text()
    assert "my_service_function" in src

def test_generated_file_still_valid_python(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture
    import uuid

    @capture("validity_test")
    def fn():
        return {
            "ts":  datetime.datetime.now(),
            "uid": uuid.uuid4(),
            "dec": decimal.Decimal("9.99"),
            "b":   b"\x00\xff",
        }

    fn()
    for f in tmp_path.glob("snapfix_*.py"):
        ast.parse(f.read_text())  # must not raise

def test_pii_review_warning_in_header(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("review_warning_test")
    def fn():
        return {"email": "x@y.com", "plan": "pro"}

    fn()
    src = list(tmp_path.glob("snapfix_*.py"))[0].read_text()
    assert "Review before committing" in src or "value-level PII" in src
