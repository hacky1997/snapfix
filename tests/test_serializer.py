"""
Tests for snapfix.serializer — the recursive JSON serializer.

Covers: all supported types, circular references, depth/size guards,
unserializable fallback, determinism, and roundtrip identity.
"""
import dataclasses
import datetime
import decimal
import enum
import math
import pathlib
import uuid

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

from snapfix.serializer import (
    SnapfixSerializer,
    _MARKER,
    _UNSZ,
    _CIRC,
    _TRUNC,
    _DEPTH,
)

S = SnapfixSerializer()


# ── Primitives ────────────────────────────────────────────────────────────────

def test_serialize_none():
    assert S.serialize(None) is None

def test_serialize_bool():
    assert S.serialize(True) is True
    assert S.serialize(False) is False

def test_serialize_int():
    assert S.serialize(42) == 42
    assert S.serialize(-1) == -1

def test_serialize_float():
    assert S.serialize(3.14) == 3.14

def test_serialize_string():
    assert S.serialize("hello") == "hello"
    assert S.serialize("") == ""

def test_serialize_nested_dict():
    d = {"a": {"b": {"c": 42}}}
    assert S.serialize(d) == d

def test_serialize_list_of_dicts():
    d = [{"x": 1}, {"x": 2}]
    assert S.serialize(d) == d


# ── Date / time types ─────────────────────────────────────────────────────────

def test_serialize_datetime():
    dt = datetime.datetime(2026, 1, 15, 12, 0, 0)
    r  = S.serialize(dt)
    assert r[_MARKER] == "datetime"
    assert S.deserialize(r) == dt

def test_serialize_date():
    d = datetime.date(2026, 1, 15)
    r = S.serialize(d)
    assert r[_MARKER] == "date"
    assert S.deserialize(r) == d

def test_serialize_time():
    t = datetime.time(14, 30, 0)
    r = S.serialize(t)
    assert r[_MARKER] == "time"
    assert S.deserialize(r) == t

def test_serialize_timedelta():
    td = datetime.timedelta(seconds=3661)
    r  = S.serialize(td)
    assert r[_MARKER] == "timedelta"
    assert S.deserialize(r) == td


# ── Other stdlib types ────────────────────────────────────────────────────────

def test_serialize_uuid():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    r = S.serialize(u)
    assert r[_MARKER] == "uuid"
    assert S.deserialize(r) == u

def test_serialize_decimal():
    d = decimal.Decimal("99.99")
    r = S.serialize(d)
    assert r[_MARKER] == "decimal"
    assert S.deserialize(r) == d

def test_serialize_bytes():
    b = b"\x00\xff\xfe"
    r = S.serialize(b)
    assert r[_MARKER] == "bytes"
    assert S.deserialize(r) == b

def test_serialize_bytearray():
    ba = bytearray(b"\x01\x02")
    r  = S.serialize(ba)
    assert r[_MARKER] == "bytearray"
    assert S.deserialize(r) == ba

def test_serialize_path():
    p = pathlib.Path("/tmp/test.txt")
    r = S.serialize(p)
    assert r[_MARKER] == "path"
    assert S.deserialize(r) == p


# ── Collections ───────────────────────────────────────────────────────────────

def test_serialize_enum():
    class Color(enum.Enum):
        RED = "red"
    r = S.serialize(Color.RED)
    assert r[_MARKER] == "enum"

def test_serialize_set_is_deterministic():
    s1 = S.serialize({3, 1, 2})
    s2 = S.serialize({1, 3, 2})
    assert s1 == s2

def test_serialize_frozenset():
    r = S.serialize(frozenset({1, 2}))
    assert r[_MARKER] == "frozenset"

def test_serialize_tuple_becomes_list():
    """Tuples become lists on roundtrip — documented behavior."""
    t = (1, "a", None)
    r = S.serialize(t)
    assert r[_MARKER] == "tuple"
    assert S.deserialize(r) == list(t)
    assert isinstance(S.deserialize(r), list)


# ── Special float values ──────────────────────────────────────────────────────

def test_serialize_nan():
    r = S.serialize(float("nan"))
    assert r[_MARKER] == "float"
    assert r["value"] == "nan"
    assert math.isnan(S.deserialize(r))

def test_serialize_inf():
    r = S.serialize(float("inf"))
    assert r["value"] == "inf"

def test_serialize_neg_inf():
    r = S.serialize(float("-inf"))
    assert r["value"] == "-inf"


# ── Structured types ──────────────────────────────────────────────────────────

@dataclasses.dataclass
class SampleDC:
    x: int
    y: str

def test_serialize_dataclass():
    r = S.serialize(SampleDC(x=1, y="hi"))
    assert r == {"x": 1, "y": "hi"}


try:
    from pydantic import BaseModel

    class SampleModel(BaseModel):
        name: str
        score: float

    def test_serialize_pydantic_v2():
        r = S.serialize(SampleModel(name="alice", score=0.9))
        assert r == {"name": "alice", "score": 0.9}

except ImportError:
    pass


# ── Safety guards ─────────────────────────────────────────────────────────────

def test_serialize_unserializable_type():
    class Weird:
        __slots__ = ()
    r = S.serialize(Weird())
    assert _UNSZ in r

def test_serialize_circular_reference():
    d: dict = {}
    d["self"] = d
    r = S.serialize(d)
    assert r["self"].get(_CIRC) is True

def test_serialize_circular_list():
    lst = [1, 2]
    lst.append(lst)  # type: ignore
    r = S.serialize(lst)
    assert any(isinstance(x, dict) and _CIRC in x for x in r)

def test_serialize_max_depth_no_crash():
    nested: dict = {"a": 1}
    for _ in range(15):
        nested = {"x": nested}
    result = S.serialize(nested)
    assert isinstance(result, dict)

def test_serialize_max_size_no_crash():
    big = {"k" + str(i): "v" * 500 for i in range(2000)}
    s   = SnapfixSerializer(max_size_bytes=500)
    assert s.serialize(big) is not None


# ── Roundtrip identity ────────────────────────────────────────────────────────

def test_deserialize_roundtrip_identity():
    original = {
        "ts":  datetime.datetime(2026, 1, 1, 12, 0, 0),
        "uid": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "dec": decimal.Decimal("1.5"),
        "b":   b"data",
        "p":   pathlib.Path("/tmp"),
    }
    rt = S.deserialize(S.serialize(original))
    assert rt["ts"]  == original["ts"]
    assert rt["uid"] == original["uid"]
    assert rt["dec"] == original["dec"]
    assert rt["b"]   == original["b"]
    assert rt["p"]   == original["p"]


# ── Property-based tests ──────────────────────────────────────────────────────

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
    if data is not None:
        assert result is not None
