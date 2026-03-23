"""
Tests for snapfix.scrubber — the PII field scrubber.

Covers: top-level, nested, list, case-insensitive, substring matching,
non-mutation, numeric fields, audit trail, and hypothesis property tests.
"""
import copy

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

from snapfix.scrubber import SnapfixScrubber, _SCRUBBED_STR, _SCRUBBED_NUM

SC = SnapfixScrubber(["email", "token", "password"])


def test_scrub_top_level_email():
    r, keys = SC.scrub({"email": "x@y.com", "name": "Alice"})
    assert r["email"] == _SCRUBBED_STR
    assert r["name"]  == "Alice"
    assert "email" in keys

def test_scrub_nested_email():
    r, _ = SC.scrub({"user": {"email": "x@y.com", "id": 1}})
    assert r["user"]["email"] == _SCRUBBED_STR
    assert r["user"]["id"]    == 1

def test_scrub_email_in_list_of_dicts():
    r, _ = SC.scrub([{"email": "a"}, {"email": "b"}])
    assert all(x["email"] == _SCRUBBED_STR for x in r)

def test_scrub_case_insensitive_key():
    r, _ = SC.scrub({"EMAIL": "x@y.com"})
    assert r["EMAIL"] == _SCRUBBED_STR

def test_scrub_substring_match():
    """'customer_email' contains 'email' — must be scrubbed."""
    r, keys = SC.scrub({"customer_email": "x@y.com"})
    assert r["customer_email"] == _SCRUBBED_STR
    assert "customer_email" in keys

def test_scrub_does_not_modify_input():
    """CRITICAL: scrub() must never mutate the input dict."""
    original   = {"email": "x@y.com", "name": "Alice"}
    before_copy = copy.deepcopy(original)
    SC.scrub(original)
    assert original == before_copy

def test_scrub_returns_scrubbed_keys():
    _, keys = SC.scrub({"email": "a", "token": "b", "name": "c"})
    assert "email" in keys
    assert "token" in keys
    assert "name"  not in keys

def test_scrub_numeric_field():
    sc = SnapfixScrubber(["token"])
    r, _ = sc.scrub({"token": 99999})
    assert r["token"] == _SCRUBBED_NUM

def test_scrub_empty_dict():
    r, keys = SC.scrub({})
    assert r == {}
    assert keys == []

def test_scrub_none_value():
    r, keys = SC.scrub({"email": None})
    assert r["email"] == _SCRUBBED_STR
    assert "email" in keys

def test_scrub_deeply_nested():
    d = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"email": "x"}}}}}}}}
    r, keys = SC.scrub(d)
    assert r["a"]["b"]["c"]["d"]["e"]["f"]["g"]["email"] == _SCRUBBED_STR

def test_scrub_non_target_field_unchanged():
    r, _ = SC.scrub({"name": "Bob", "retry_count": 3})
    assert r["name"]        == "Bob"
    assert r["retry_count"] == 3

def test_scrub_custom_fields():
    sc = SnapfixScrubber(["billing_name", "tax_id"])
    r, keys = sc.scrub({"billing_name": "Alice", "order_id": "X1"})
    assert r["billing_name"] == _SCRUBBED_STR
    assert r["order_id"]     == "X1"

def test_scrub_key_path_in_audit():
    _, keys = SC.scrub({"user": {"email": "x"}})
    assert "user.email" in keys


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
@settings(max_examples=150, deadline=None)
def test_scrubber_never_mutates_input(data):
    original = copy.deepcopy(data)
    SC.scrub(data)
    assert data == original
