import ast
import asyncio
import base64
import dataclasses
import datetime
import decimal
import enum
import math
import os
import pathlib
import sys
import uuid
import warnings

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

from snapfix.serializer import SnapfixSerializer, _MARKER, _UNSZ, _CIRC, _TRUNC, _DEPTH
from snapfix.scrubber import SnapfixScrubber, _SCRUBBED_STR, _SCRUBBED_NUM
from snapfix.codegen import SnapfixCodegen
from snapfix.config import SnapfixConfig
from snapfix.store import SnapfixStore

S = SnapfixSerializer()


# ── Serializer -- primitives ─────────────────────────────────────────────────

def test_primitives():
    for v in [None, True, False, 0, -1, 3.14, "", "hello"]:
        assert S.serialize(v) == v


def test_nested_dict():
    d = {"a": {"b": {"c": 42}}}
    assert S.serialize(d) == d


def test_list_of_dicts():
    d = [{"x": 1}, {"x": 2}]
    assert S.serialize(d) == d


def test_datetime():
    dt = datetime.datetime(2026, 1, 15, 12, 0, 0)
    r = S.serialize(dt)
    assert r[_MARKER] == "datetime"
    assert S.deserialize(r) == dt


def test_date():
    d = datetime.date(2026, 1, 15)
    r = S.serialize(d)
    assert r[_MARKER] == "date"
    assert S.deserialize(r) == d


def test_uuid():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    r = S.serialize(u)
    assert r[_MARKER] == "uuid"
    assert S.deserialize(r) == u


def test_decimal():
    d = decimal.Decimal("99.99")
    r = S.serialize(d)
    assert r[_MARKER] == "decimal"
    assert S.deserialize(r) == d


def test_bytes():
    b = b"\x00\xff\xfe"
    r = S.serialize(b)
    assert r[_MARKER] == "bytes"
    assert S.deserialize(r) == b


def test_path():
    p = pathlib.Path("/tmp/test.txt")
    r = S.serialize(p)
    assert r[_MARKER] == "path"
    assert S.deserialize(r) == p


def test_enum():
    class Color(enum.Enum):
        RED = "red"

    r = S.serialize(Color.RED)
    assert r[_MARKER] == "enum"


def test_set_is_deterministic():
    s1 = S.serialize({3, 1, 2})
    s2 = S.serialize({1, 3, 2})
    assert s1 == s2


def test_tuple():
    t = (1, "a", None)
    r = S.serialize(t)
    assert r[_MARKER] == "tuple"
    # tuples become lists on roundtrip -- documented behavior
    assert S.deserialize(r) == list(t)


def test_nan_inf():
    assert S.serialize(float("nan"))[_MARKER] == "float"
    assert S.serialize(float("inf"))["value"] == "inf"
    assert S.serialize(float("-inf"))["value"] == "-inf"


@dataclasses.dataclass
class MyDC:
    x: int
    y: str


def test_dataclass():
    r = S.serialize(MyDC(x=1, y="hi"))
    assert r == {"x": 1, "y": "hi"}


def test_unserializable_has_marker():
    class Weird:
        __slots__ = ()

    r = S.serialize(Weird())
    assert _UNSZ in r


def test_circular_reference():
    d: dict = {}
    d["self"] = d
    r = S.serialize(d)
    assert r["self"].get(_CIRC) is True


def test_max_depth_no_crash():
    nested = {"a": 1}
    for _ in range(15):
        nested = {"x": nested}
    result = S.serialize(nested)
    assert isinstance(result, dict)


def test_max_size_no_crash():
    big = {"k" + str(i): "v" * 500 for i in range(2000)}
    s = SnapfixSerializer(max_size_bytes=500)
    result = s.serialize(big)
    assert result is not None


def test_deserialize_roundtrip():
    original = {
        "ts":  datetime.datetime(2026, 1, 1, 12, 0, 0),
        "uid": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "dec": decimal.Decimal("1.5"),
        "b":   b"data",
        "p":   pathlib.Path("/tmp"),
    }
    r = S.deserialize(S.serialize(original))
    assert r["ts"]  == original["ts"]
    assert r["uid"] == original["uid"]
    assert r["dec"] == original["dec"]
    assert r["b"]   == original["b"]
    assert r["p"]   == original["p"]


# pydantic v2 if available
try:
    from pydantic import BaseModel

    class PM(BaseModel):
        name: str
        score: float

    def test_pydantic_v2():
        r = S.serialize(PM(name="alice", score=0.9))
        assert r == {"name": "alice", "score": 0.9}

except ImportError:
    pass


# ── Scrubber ─────────────────────────────────────────────────────────────────

SC = SnapfixScrubber(["email", "token", "password"])


def test_scrub_top_level():
    d = {"email": "x@y.com", "name": "Alice"}
    r, keys = SC.scrub(d)
    assert r["email"] == _SCRUBBED_STR
    assert r["name"] == "Alice"
    assert "email" in keys


def test_scrub_nested():
    d = {"user": {"email": "x@y.com", "id": 1}}
    r, keys = SC.scrub(d)
    assert r["user"]["email"] == _SCRUBBED_STR
    assert r["user"]["id"] == 1


def test_scrub_list_of_dicts():
    d = [{"email": "a"}, {"email": "b"}]
    r, _ = SC.scrub(d)
    assert all(x["email"] == _SCRUBBED_STR for x in r)


def test_scrub_case_insensitive():
    d = {"EMAIL": "x@y.com"}
    r, _ = SC.scrub(d)
    assert r["EMAIL"] == _SCRUBBED_STR


def test_scrub_does_not_mutate():
    original = {"email": "x@y.com"}
    copy_ref = {"email": "x@y.com"}
    SC.scrub(original)
    assert original == copy_ref


def test_scrub_numeric():
    sc = SnapfixScrubber(["token"])
    d = {"token": 99999}
    r, _ = sc.scrub(d)
    assert r["token"] == _SCRUBBED_NUM


def test_scrub_none_value():
    d = {"email": None}
    r, keys = SC.scrub(d)
    assert r["email"] == _SCRUBBED_STR
    assert "email" in keys


def test_scrub_substring_match():
    d = {"customer_email": "x@y.com"}
    r, keys = SC.scrub(d)
    assert r["customer_email"] == _SCRUBBED_STR


def test_scrub_returns_all_keys():
    d = {"email": "a", "token": "b", "name": "c"}
    _, keys = SC.scrub(d)
    assert "email" in keys and "token" in keys
    assert "name" not in keys


# ── Codegen ───────────────────────────────────────────────────────────────────

CG = SnapfixCodegen()


def test_codegen_valid_python():
    src = CG.generate("my_fixture", {"x": 1}, [], datetime.datetime.utcnow())
    ast.parse(src)


def test_codegen_has_pytest_fixture():
    src = CG.generate("my_fixture", {"x": 1}, [], datetime.datetime.utcnow())
    assert "@pytest.fixture" in src


def test_codegen_sanitizes_name():
    src = CG.generate("my-bad.name!2", {}, [], datetime.datetime.utcnow())
    ast.parse(src)


def test_codegen_records_scrubbed_fields():
    src = CG.generate("f", {}, ["email", "token"], datetime.datetime.utcnow())
    assert "email" in src


def test_codegen_nested_dict():
    data = {"a": {"b": [1, 2, 3]}, "ts": datetime.datetime(2026, 1, 1).isoformat()}
    src = CG.generate("nested", data, [], datetime.datetime.utcnow())
    ast.parse(src)


# ── Capture (sync + async) ────────────────────────────────────────────────────

def test_capture_sync(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"] = "true"
    # clear module cache
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]
    from snapfix import capture

    @capture("test_sync")
    def fn():
        return {"status": "ok"}

    result = fn()
    assert result == {"status": "ok"}
    assert any(tmp_path.glob("snapfix_*.py"))


def test_capture_preserves_return_value(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"] = "true"
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]
    from snapfix import capture

    sentinel = {"unique_key": 42, "list": [1, 2, 3]}

    @capture("preserve_test")
    def fn():
        return sentinel

    assert fn() is sentinel


def test_capture_preserves_exception(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"] = "true"
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]
    from snapfix import capture

    @capture("exc_test")
    def fn():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        fn()
    # no fixture written on exception
    assert not any(tmp_path.glob("snapfix_*.py"))


def test_capture_disabled(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"] = "false"
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]
    from snapfix import capture

    @capture("disabled_test")
    def fn():
        return {"x": 1}

    fn()
    assert not any(tmp_path.glob("snapfix_*.py"))
    os.environ["SNAPFIX_ENABLED"] = "true"


def test_capture_async(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"] = "true"
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]
    from snapfix import capture

    @capture("async_test")
    async def afn():
        return {"async": True}

    asyncio.run(afn())
    assert any(tmp_path.glob("snapfix_*.py"))


def test_capture_preserves_async_signature(tmp_path):
    os.environ["SNAPFIX_OUTPUT_DIR"] = str(tmp_path)
    os.environ["SNAPFIX_ENABLED"] = "true"
    for m in list(sys.modules):
        if "snapfix" in m:
            del sys.modules[m]
    from snapfix import capture

    @capture("sig_test")
    async def original_name():
        return {}

    assert original_name.__name__ == "original_name"
    assert asyncio.iscoroutinefunction(original_name)


# ── Store ────────────────────────────────────────────────────────────────────

def test_store_write_and_list(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("my_fix", "@pytest.fixture\ndef my_fix(): return {}", {"ts": "2026"})
    entries = store.list()
    assert len(entries) == 1


def test_store_delete(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("del_fix", "# code", {})
    assert store.exists("del_fix")
    store.delete("del_fix")
    assert not store.exists("del_fix")


def test_store_atomic_write(tmp_path):
    store = SnapfixStore(tmp_path)
    store.write("atomic", "content", {})
    # No .tmp file should remain
    assert not list(tmp_path.glob("*.tmp"))


# ── Hypothesis ────────────────────────────────────────────────────────────────

_primitives = st.one_of(
    st.none(), st.booleans(),
    st.integers(-1000, 1000),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=30),
)
_json_vals = st.recursive(
    _primitives,
    extend=lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(max_size=8, alphabet="abcdef"), children, max_size=4)
    ),
    max_leaves=15,
)


@given(_json_vals)
@settings(max_examples=300, deadline=None)
def test_serializer_never_crashes(data):
    result = SnapfixSerializer(max_depth=5, max_size_bytes=10_000).serialize(data)
    # None is a valid result when data is None — the serializer must not raise,
    # and must return something for every non-None input
    if data is not None:
        assert result is not None


@given(_json_vals)
@settings(max_examples=150, deadline=None)
def test_scrubber_never_mutates(data):
    import copy
    original = copy.deepcopy(data)
    SC.scrub(data)
    assert data == original


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
