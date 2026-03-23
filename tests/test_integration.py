"""
Integration tests for snapfix.

Tests the full pipeline end-to-end:
  @capture → serializer → scrubber → codegen → store → importable fixture
"""
import ast
import asyncio
import dataclasses
import datetime
import decimal
import importlib.util
import os
import pathlib
import sys
import types
import uuid

import pytest

# Stub pytest.fixture so the generated file can be imported in tests
_fake_pytest = types.ModuleType("pytest")
_fake_pytest.fixture = lambda f: f  # type: ignore
sys.modules.setdefault("pytest", _fake_pytest)


def _reload_snapfix():
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]


def _import_fixture_file(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("_fx_tmp", path)
    mod  = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules["_fx_tmp"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_full_pipeline_simple_dict(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload_snapfix()
    from snapfix import capture

    @capture("user_profile")
    def get_user():
        return {"id": 1, "name": "Alice", "email": "alice@example.com"}

    get_user()

    fx_files = list(tmp_path.glob("snapfix_*.py"))
    assert fx_files, "No fixture file written"

    src = fx_files[0].read_text()
    ast.parse(src)
    assert "***SCRUBBED***" in src     # email scrubbed
    assert "Alice" in src              # name kept


def test_full_pipeline_pii_scrubbed(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload_snapfix()
    from snapfix import capture

    @capture("payment", scrub=["card_last4"])
    def get_payment():
        return {
            "amount": 99.99,
            "token": "tok_abc123",
            "card_last4": "4242",
            "currency": "usd",
        }

    get_payment()

    src = list(tmp_path.glob("snapfix_*.py"))[0].read_text()
    assert src.count("***SCRUBBED***") >= 2  # token + card_last4
    assert "usd" in src
    assert "99.99" in src


def test_full_pipeline_complex_types_roundtrip(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload_snapfix()
    from snapfix import capture, reconstruct

    @capture("complex_obj")
    def get_complex():
        return {
            "ts":  datetime.datetime(2026, 3, 1, 12, 0, 0),
            "uid": uuid.UUID("12345678-1234-5678-1234-567812345678"),
            "dec": decimal.Decimal("149.99"),
        }

    get_complex()

    fx = list(tmp_path.glob("snapfix_*.py"))[0]
    mod = _import_fixture_file(fx)
    fn_name = [n for n in dir(mod)
               if not n.startswith("_") and callable(getattr(mod, n))
               and n not in ("reconstruct", "fixture")][0]
    result = getattr(mod, fn_name)()

    assert isinstance(result["ts"],  datetime.datetime)
    assert isinstance(result["uid"], uuid.UUID)
    assert isinstance(result["dec"], decimal.Decimal)
    assert result["ts"]  == datetime.datetime(2026, 3, 1, 12, 0, 0)
    assert result["dec"] == decimal.Decimal("149.99")

    sys.modules.pop("_fx_tmp", None)


@dataclasses.dataclass
class OrderItem:
    product: str
    quantity: int
    price: decimal.Decimal


def test_full_pipeline_dataclass(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload_snapfix()
    from snapfix import capture

    @capture("order_item")
    def get_item():
        return OrderItem(product="Widget", quantity=3, price=decimal.Decimal("9.99"))

    get_item()

    src = list(tmp_path.glob("snapfix_*.py"))[0].read_text()
    assert "Widget" in src
    assert "9.99"   in src


def test_full_pipeline_async_function(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload_snapfix()
    from snapfix import capture

    @capture("async_result")
    async def fetch():
        return {"data": "from async", "status": 200}

    asyncio.run(fetch())
    assert any(tmp_path.glob("snapfix_*.py"))


def test_full_pipeline_exception_leaves_no_file(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload_snapfix()
    from snapfix import capture

    @capture("will_fail")
    def broken():
        raise RuntimeError("downstream error")

    with pytest.raises(RuntimeError):
        broken()
    assert not any(tmp_path.glob("snapfix_*.py"))


def test_generated_fixture_file_parses_as_valid_python(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"]    = "true"
    _reload_snapfix()
    from snapfix import capture

    @capture("parse_check")
    def fn():
        return {
            "nested": {"list": [1, None, True, "text"]},
            "email": "should@be.scrubbed",
        }

    fn()
    for f in tmp_path.glob("snapfix_*.py"):
        ast.parse(f.read_text())  # must not raise
