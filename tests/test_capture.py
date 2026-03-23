"""
Tests for snapfix.capture — the @capture decorator.

Covers: sync functions, async functions, return value preservation,
exception safety, disabled state, and overwrite behaviour.
"""
import asyncio
import os
import pathlib
import sys

import pytest

# Each test reloads snapfix to pick up env var changes
def _reload():
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]


def test_capture_sync_function(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("sync_test")
    def fn():
        return {"status": "ok"}

    result = fn()
    assert result == {"status": "ok"}
    assert any(tmp_path.glob("snapfix_*.py"))


def test_capture_preserves_return_value(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    sentinel = {"unique": 42, "nested": [1, 2, 3]}

    @capture("preserve_test")
    def fn():
        return sentinel

    assert fn() is sentinel


def test_capture_preserves_function_name(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("name_test")
    def my_actual_function():
        return {}

    assert my_actual_function.__name__ == "my_actual_function"


def test_capture_with_exception_does_not_write_fixture(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("exc_test")
    def fn():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        fn()
    assert not any(tmp_path.glob("snapfix_*.py"))


def test_capture_disabled_via_env(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "false"
    _reload()
    from snapfix import capture

    @capture("disabled_test")
    def fn():
        return {"x": 1}

    fn()
    assert not any(tmp_path.glob("snapfix_*.py"))
    os.environ["SNAPFIX_ENABLED"] = "true"


def test_capture_async_function(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("async_test")
    async def afn():
        return {"async": True}

    asyncio.run(afn())
    assert any(tmp_path.glob("snapfix_*.py"))


def test_capture_async_is_still_coroutine(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("coro_test")
    async def afn():
        return {}

    assert asyncio.iscoroutinefunction(afn)


def test_capture_async_preserves_name(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("name_test")
    async def my_async_function():
        return {}

    assert my_async_function.__name__ == "my_async_function"


def test_capture_overwrites_existing_fixture(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("overwrite_test")
    def fn():
        return {"version": 1}

    fn()
    files_after_first = list(tmp_path.glob("snapfix_*.py"))
    assert len(files_after_first) == 1

    fn()
    files_after_second = list(tmp_path.glob("snapfix_*.py"))
    assert len(files_after_second) == 1  # still one file, not two


def test_capture_with_none_return(tmp_path):
    """Returning None is valid and should produce a fixture."""
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("none_return")
    def fn():
        return None

    result = fn()
    assert result is None
    assert any(tmp_path.glob("snapfix_*.py"))


def test_capture_with_extra_scrub_fields(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload()
    from snapfix import capture

    @capture("scrub_test", scrub=["billing_name"])
    def fn():
        return {"billing_name": "Alice", "plan": "pro"}

    fn()
    fixture_files = list(tmp_path.glob("snapfix_*.py"))
    assert fixture_files
    content = fixture_files[0].read_text()
    assert "***SCRUBBED***" in content
    assert "pro" in content
