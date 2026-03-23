# Contributing to snapfix

Thank you for your interest. Please read this before opening a PR.

---

## Scope

snapfix does exactly three things: capture Python objects, scrub PII by field name,
and emit `@pytest.fixture` files. PRs that expand this scope will be declined.

**Explicitly out of scope for snapfix:**
- Database row capture (separate tool)
- HTTP request/response recording (use vcrpy)
- NLP-based or value-level PII detection
- Binary serialization formats (msgpack, cbor, pickle)
- Snapshot diffing or regression detection
- Web UI or dashboards
- Support for Python < 3.10

If you have an idea that does not fit snapfix's scope, consider opening a
discussion before writing code.

---

## Development setup

```bash
git clone https://github.com/yourname/snapfix
cd snapfix
pip install -e ".[dev]"
pytest
ruff check src/
```

---

## Before opening a PR

1. **Tests are required.** Every change to `src/snapfix/` must be covered by a
   corresponding test in `tests/test_snapfix.py`. PRs without tests will not be
   reviewed.

2. **The serialization contract is public.** The `__snapfix_type__` marker format
   in `serializer.py` is a public API from v1.0.0 onwards. Changes that alter
   the format of existing markers are breaking changes and require a major version bump.

3. **The scrubber must not mutate inputs.** `SnapfixScrubber.scrub()` must always
   return a deep copy. Tests enforce this. Do not change this behaviour.

4. **Exception safety in `capture`.** The `_record()` function in `capture.py`
   must never raise. Failures emit `warnings.warn()` and return silently.
   Do not remove this guarantee.

5. **Run `ruff check src/` and `mypy src/snapfix/` before submitting.**

---

## Reporting bugs

Open a GitHub issue with:
- Python version
- snapfix version (`pip show snapfix`)
- Minimal reproducer (object type, decorator usage)
- Actual vs. expected behaviour

Do not include real production data in bug reports.

---

## PII scrubbing PRs

PRs that add new default scrub fields are welcome if the field name pattern is
unambiguous and broadly applicable. PRs that change substring matching behaviour
to exact matching are breaking changes.

PRs adding value-level PII detection (e.g. regex scanning of string values) are
out of scope for the core package. They belong in an optional integration
(`pip install snapfix[presidio]`), which is a future roadmap item.
