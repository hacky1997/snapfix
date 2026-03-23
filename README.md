# snapfix

**Capture real Python objects from a test environment, strip sensitive data automatically, and write reusable test fixtures — with one decorator.**

[![CI](https://github.com/hacky1997/snapfix/actions/workflows/ci.yml/badge.svg)](https://github.com/hacky1997/snapfix/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/snapfix.svg)](https://pypi.org/project/snapfix/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/snapfix.svg)](https://pypi.org/project/snapfix/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Background — what problem does this solve?

When writing automated tests in Python, you need sample data: a realistic API response, a database record, a parsed object. That sample data is called a **pytest fixture** — a reusable block of test data that pytest (Python's testing framework) injects automatically into any test that asks for it by name.

Getting that data safely is harder than it sounds. Two common approaches both have serious problems:

- **Hand-write fake data.** Fast, but you'll guess the shape wrong. Real APIs return dozens of fields you didn't know existed. When your made-up fixture doesn't match what the API actually returns, your tests pass and production still breaks.
- **Copy-paste a real API response.** Accurate, but dangerous. Real responses contain customer emails, API tokens, and personal details — collectively called **PII (personally identifiable information)**. Once that data ends up in your git history, it stays there permanently even if you delete the file later.

snapfix is a third option: capture the real object automatically, strip the sensitive fields before anything is written to disk, and generate the fixture file for you.

---

## The problem in one sentence

You hit a bug that only reproduces with real data, you need a reliable test, and you can't safely paste the live payload.

---

## How it works in 30 seconds

```python
# Step 1 — Add @capture above any function you want to snapshot.
# The @capture syntax is called a "decorator" — it wraps the function to add
# behaviour (capturing output) without changing what the function itself does.
from snapfix import capture

@capture("invoice_response", scrub=["billing_name"])
#         ^-- name for the generated fixture file
#                              ^-- extra sensitive fields to strip beyond the defaults
def fetch_invoice(invoice_id: str) -> dict:
    return external_api.get(f"/invoices/{invoice_id}")
```

```bash
# Step 2 — Call it once against your staging environment.
# "Staging" is a test copy of your live system — real data flows through it,
# but no real users are affected.
python -c "from myapp.billing import fetch_invoice; fetch_invoice('INV-8821')"
```

```
snapfix ✓  fixture written: tests/fixtures/snapfix_invoice_response.py
snapfix    scrubbed: customer.email, meta.token, billing_name
snapfix    review before committing — value-level PII is not detected
```

```python
# Step 3 — Use the fixture in any test. pytest provides it automatically by name.
from decimal import Decimal

def test_invoice_total(invoice_response):  # pytest matches the parameter name to the fixture
    assert invoice_response["amount"].quantize(Decimal("0.01")) == Decimal("149.99")
```

Remove `@capture` from your function once the fixture is committed. Done.

---

## Why this exists

Hand-written fixtures have two failure modes:

- **Wrong shape.** You guessed the API response structure. You missed `amount_due` vs `amount`, or that `customer` is sometimes a string ID and sometimes a full nested object. The fixture passes, production still breaks.
- **PII in git history.** The fastest path to a real fixture is printing a live API response and pasting it. The result is customer emails and tokens committed to your repository. `git history` does not forget.

snapfix eliminates both by capturing the actual object your code returns and stripping sensitive fields before writing anything to disk.

---

## Install

```bash
pip install snapfix
```

Python 3.10+ required. No API keys. No external services. Two runtime dependencies (`typer`, `pyyaml`).

---

## Quick start

### Step 1 — Add the decorator

```python
# myapp/billing.py
from snapfix import capture

@capture(
    "stripe_invoice_paid",  # the fixture will be named stripe_invoice_paid()
    scrub=["metadata"],     # strip this field in addition to the 22 sensitive defaults
)
async def fetch_invoice(invoice_id: str) -> dict:
    invoice = await stripe.Invoice.retrieve(invoice_id, expand=["customer"])
    return invoice.to_dict()
```

Works on both sync and async functions. The decorator is transparent — the return value is always unchanged, and if the function raises an exception, it propagates normally with no fixture written.

### Step 2 — Call it once in your staging environment

```bash
python -c "
import asyncio
from myapp.billing import fetch_invoice
asyncio.run(fetch_invoice('in_1OkRealInvoiceId'))
"
```

snapfix writes `tests/fixtures/snapfix_stripe_invoice_paid.py`:

```python
# Generated by snapfix — do not edit manually
# Regenerate  : re-run the @capture decorated function
# Captured    : 2026-03-24T14:22:01
# Source      : myapp.billing.fetch_invoice (myapp/billing.py)
# Scrubbed    : customer.email, customer.address, metadata.internal_ref
#
# ⚠  Review before committing: value-level PII is not detected.
#    All scrubbed fields are listed above.
import pytest
from snapfix import reconstruct
# reconstruct() converts snapfix's internal markers back to real Python types.
# The datetime marker below, for example, becomes an actual datetime.datetime object.

@pytest.fixture
def stripe_invoice_paid():
    return reconstruct({
        'id': 'in_1OkRealInvoiceId',
        'amount_due': 14999,                  # integer cents — exactly what Stripe returns
        'amount_paid': 14999,
        'currency': 'usd',
        'status': 'paid',
        'customer_email': '***SCRUBBED***',   # stripped — "email" matches the default list
        'created': {'__snapfix_type__': 'datetime', 'value': '2026-03-01T09:00:00'},  # datetime
        'metadata': '***SCRUBBED***',         # stripped — you passed scrub=["metadata"]
    })
```

### Step 3 — Review, commit, and remove the decorator

Open the generated file. The `# Scrubbed:` header lists every field that was automatically stripped. Verify it matches what you expected. Commit the file. Remove `@capture` from your function — the fixture is self-contained from here.

### Step 4 — Write tests against the real data shape

```python
# tests/test_billing.py
import datetime
from decimal import Decimal

def test_invoice_is_paid(stripe_invoice_paid):
    assert stripe_invoice_paid["status"] == "paid"

def test_invoice_amount_in_cents(stripe_invoice_paid):
    # Stripe always returns integer cents — the fixture reflects what Stripe actually sends,
    # not what you might have assumed when writing fake data by hand.
    assert stripe_invoice_paid["amount_paid"] == 14999
    assert isinstance(stripe_invoice_paid["amount_paid"], int)

def test_pii_is_scrubbed(stripe_invoice_paid):
    # Confirm sensitive fields were removed — documents your compliance behaviour.
    assert stripe_invoice_paid["customer_email"] == "***SCRUBBED***"

def test_created_is_datetime(stripe_invoice_paid):
    # reconstruct() restored the original Python type — not a string, not a raw timestamp.
    assert isinstance(stripe_invoice_paid["created"], datetime.datetime)
```

---

## PII scrubbing

> **⚠ Important limitation:** snapfix scrubs by **field name only**. It does not scan field values. An email address stored as `response["tags"][0]` — inside a list under a non-obvious key — will **not** be stripped automatically. Always review the generated file before committing.

PII stands for **personally identifiable information**: anything that could identify a real person, such as an email address, phone number, or payment card number.

### Default scrubbed field names

Any key whose name contains one of these strings (case-insensitive, substring match) is replaced automatically:

`email` · `password` · `passwd` · `token` · `secret` · `api_key` · `apikey` · `access_token` · `refresh_token` · `ssn` · `credit_card` · `card_number` · `cvv` · `phone` · `mobile` · `dob` · `date_of_birth` · `address` · `ip_address` · `authorization` · `auth` · `bearer`

**How substring matching works:**

| Field name | Scrubbed? | Reason |
|---|---|---|
| `customer_email` | ✓ yes | contains `email` |
| `billing_phone_number` | ✓ yes | contains `phone` |
| `retry_count` | ✗ no | no match |
| `metadata` | ✗ no by default | add via `scrub=["metadata"]` |

### Adding custom fields

```python
@capture("order", scrub=["customer_id", "tax_number", "metadata"])
def fetch_order(order_id: str) -> dict: ...
```

### Replacement values

| Original field type | Replaced with |
|---|---|
| `str` | `"***SCRUBBED***"` |
| `int` / `float` | `-1` |
| `None` | `"***SCRUBBED***"` |

---

## Supported Python types

snapfix can capture any of the types below. `reconstruct()` — the function called inside every generated fixture — converts them back to their original Python type automatically. You never need to cast types manually in your tests.

**"Round-trips as" means:** you capture type X → it is stored safely in the fixture file → when the test runs, you get type X back.

| Type | Round-trips as | Note |
|---|---|---|
| `dict`, `list`, `str`, `int`, `float`, `bool`, `None` | Same | Standard JSON types, no conversion needed |
| `datetime.datetime` / `.date` / `.time` / `.timedelta` | Same | Stored as ISO 8601 string internally |
| `uuid.UUID` | `UUID` | Stored as string internally |
| `decimal.Decimal` | `Decimal` | Preserves exact decimal precision — important for money |
| `bytes` / `bytearray` | Same | Stored as base64 internally |
| `pathlib.Path` | `Path` | Stored as string internally |
| `enum.Enum` | `.value` only | The enum class itself is not preserved — see Limitations |
| `tuple` | `list` | JSON has no tuple type — this is intentional, see Limitations |
| `set` / `frozenset` | `set` / `frozenset` | Stored as sorted list internally |
| `dataclass` | `dict` | Uses `dataclasses.asdict()` under the hood |
| `pydantic.BaseModel` | `dict` | Uses `.model_dump()` under the hood |
| Circular reference | Marker dict | `{"__snapfix_circular__": true}` — capture still completes |
| Unserializable type | Marker dict | `{"__snapfix_unserializable__": true, ...}` — rest of object still captured |

---

## pytest plugin

> **New to pytest plugins?** A pytest plugin extends pytest's behaviour — adding new command-line flags, automatically discovering test files, or injecting fixtures. snapfix installs itself as one automatically when you `pip install snapfix`. No additional setup required.

The following flags are available on every `pytest` run after install:

```
pytest --snapfix-capture          # enable capture for this session
pytest --no-snapfix-capture       # explicitly disable capture
pytest --snapfix-dir path/to/dir  # write fixtures to a different directory
```

Generated fixture files (`snapfix_*.py`) are auto-discovered — they show up in `pytest --collect-only` and `pytest --fixtures` alongside your hand-written fixtures.

**CI safety:** capture is automatically disabled in CI environments (GitHub Actions, GitLab CI, and most other platforms set `CI=true` automatically) unless `--snapfix-capture` is explicitly passed. This prevents snapshot calls from hitting your staging environment during automated test runs.

---

## CLI reference

All commands accept `--dir <path>` to target a non-default fixture directory.

### `snapfix list`

```
snapfix list [--dir PATH] [--json]
```

Lists all captured fixtures with their capture timestamp and which fields were scrubbed. Fixtures with a stored snapshot (used by `snapfix diff`) show `◉`; new ones show `○`.

### `snapfix show <name>`

```
snapfix show invoice_response
```

Prints the full contents of a fixture file to stdout.

### `snapfix diff <name>`

```
snapfix diff stripe_invoice_paid
snapfix diff stripe_invoice_paid --mode source
```

Shows what changed structurally between the last two captures of a fixture, field by field. Useful for detecting API schema changes after upgrading a third-party library or SDK. Exits with code `1` if differences are found — safe to use as a CI gate.

```
✗  Changes detected in 'stripe_invoice_paid':
--- stripe_invoice_paid (previous)
+++ stripe_invoice_paid (current)
@@ -1,3 +1,5 @@
 lines.data[0].amount: 14999
+lines.data[0].amount_excluding_tax: 14999
+lines.data[0].tax_amounts: []
```

In this example, Stripe added two new fields in a recent API version. The diff caught it before it reached production.

### `snapfix audit`

```
snapfix audit [--strict] [--quiet]
```

A second layer of defence after field-name scrubbing. Scans fixture files for common PII patterns that name-based scrubbing may have missed — email addresses, US phone numbers, Social Security Numbers, credit card numbers (Visa/Mastercard/Amex/Discover), AWS access keys, and long API-key-like strings.

Deliberately skips lines that already contain `***SCRUBBED***` or clearly use test data (`example.com`, `test@`, `dummy`, `fake`) to keep false positives low.

```
snapfix audit — tests/fixtures/
────────────────────────────────────────────────────────────
  Files scanned : 8
  Findings      : 0
  Status        : ✓ PASSED — no PII patterns detected
```

Use `--strict` to exit with code `1` on any finding. Add to your pre-commit hooks so it runs automatically before every commit:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: snapfix-audit
        name: snapfix PII audit
        entry: snapfix audit --strict
        language: system
        files: ^tests/fixtures/snapfix_.*\.py$
```

### `snapfix verify`

```
snapfix verify [--strict]
```

Confirms every fixture file in your test suite is still healthy: valid Python syntax, importable without errors, fixture function present, returns a non-None value. With `--strict`, also fails on fixtures containing internal markers that indicate the original capture was incomplete.

```
snapfix verify — tests/fixtures/
────────────────────────────────────────────────────────────
  ✓  snapfix_stripe_invoice_paid.py  [stripe_invoice_paid]
  ✓  snapfix_stripe_subscription.py  [stripe_subscription]
  ─────────────────────────────────────
  Total   : 2  |  Passed : 2
  Status  : ✓ ALL VALID
```

Add to CI alongside `pytest` so broken fixtures are caught before they cause confusing test failures:

```yaml
# .github/workflows/ci.yml
- run: snapfix verify
- run: pytest --tb=short -q
```

### `snapfix snapshots`

```
snapfix snapshots
```

Lists all stored snapshots available for `snapfix diff`.

### `snapfix clear <name>` / `snapfix clear-all`

```
snapfix clear invoice_response        # prompts for confirmation
snapfix clear invoice_response --yes  # skip confirmation
snapfix clear-all --yes
```

---

## Decorator reference

```python
@capture(
    name,                # str — fixture name; also becomes the function name in the output file
    scrub=None,          # list[str] | None — extra field names to scrub, merged with the 22 defaults
    max_depth=None,      # int | None — how many levels deep to serialize nested objects (default: 10)
    max_size_bytes=None, # int | None — skip capture if the payload exceeds this size (default: 500 KB)
    config=None,         # SnapfixConfig | None — pass a full config object to override everything
)
```

Three guarantees that make it safe to leave in non-production code:

- The return value is **always** passed through unchanged. The decorator never modifies what your function returns.
- If your function raises an exception, it propagates normally. No fixture is written.
- If serialization fails for any reason, `warnings.warn()` is emitted and your code continues. The decorator never raises its own exceptions.

---

## Configuration

### `snapfix.yaml` (place in your project root)

```yaml
snapfix:
  output_dir: tests/fixtures   # where fixture files are written
  max_depth: 10                # how many levels deep to serialize nested objects
  max_size_bytes: 500000       # skip capture if the object exceeds this size in bytes
  enabled: true                # set to false to disable all capture globally
```

### Environment variables

Useful for overriding config in CI or different environments without changing files.

| Variable | Default | Description |
|---|---|---|
| `SNAPFIX_OUTPUT_DIR` | `tests/fixtures` | Fixture output directory |
| `SNAPFIX_MAX_DEPTH` | `10` | Maximum serialization depth |
| `SNAPFIX_MAX_SIZE` | `500000` | Maximum payload size in bytes |
| `SNAPFIX_ENABLED` | `true` | Set to `false` to disable all capture |

### Priority order (highest to lowest)

1. Decorator parameters: `@capture(name, scrub=[...], max_depth=5)`
2. Environment variables
3. `snapfix.yaml`
4. Built-in defaults

### Disabling in production

```bash
SNAPFIX_ENABLED=false
```

Set this environment variable in production. The decorator becomes a no-op — zero overhead, no files written, no exceptions swallowed.

---

## ⚠️ Limitations

**PII detection is field-name only.** An email stored as `payload["tags"][0]` — inside a list under an unrecognised key — will not be stripped. `snapfix audit` adds a regex-based second pass, but it is not exhaustive. Always review generated fixtures before committing.

**Not safe against production traffic.** Use snapfix against staging or development environments only. Even with scrubbing enabled, PII hidden inside list entries or unexpected key names will not be caught.

**`tuple` becomes `list` on roundtrip.** JSON has no tuple type. This is intentional and documented. If your test checks the Python type, assert `isinstance(result, list)` rather than checking for `tuple`.

**Enum class is not preserved.** `reconstruct()` returns the `.value` of an enum (e.g. the string `"active"`), not the enum instance (e.g. `Status.ACTIVE`). If your tests check enum identity, cast manually after reading the fixture.

**Large payloads are silently skipped.** If the serialized payload exceeds `max_size_bytes` (default 500 KB), no fixture is written and a warning is emitted. Increase `SNAPFIX_MAX_SIZE` or reduce `max_depth` to capture a shallower slice of the object.

**Latency in staging.** Serialization adds overhead proportional to payload size. For typical API responses under 50 KB this is a few milliseconds. Do not set `SNAPFIX_ENABLED=true` in a production critical path.

---

## Roadmap

- `snapfix[presidio]` — optional value-level PII detection powered by Microsoft Presidio
- GitHub Actions integration — post structural diff results as PR comments on re-capture
- Type-stub generation for captured dataclass fixtures
- `snapfix upgrade` — re-capture all fixtures in batch from a recorded replay log

---

## FAQ

**What is a pytest fixture, in plain terms?**
A reusable block of test data or setup code. You define it once with `@pytest.fixture` and pytest automatically passes it into any test function that has a matching parameter name. snapfix generates these fixture files for you from real captured data.

**Can I regenerate a fixture?**
Yes. Re-run the `@capture` decorated function. The fixture file is overwritten in place, and the previous version is saved as `.prev.json` so `snapfix diff` can compare the two.

**Does it work with `pytest.mark.parametrize`?**
Yes. The generated file is a standard `@pytest.fixture`. It works with everything pytest supports.

**What happens if a field contains a type Python cannot serialize?**
It is replaced with a marker dictionary: `{"__snapfix_unserializable__": true, "__snapfix_repr__": "...", ...}`. The rest of the object is still captured. `reconstruct()` returns the marker as-is so you can see which field caused the issue.

**Does capture slow down my staging environment?**
For typical API responses under 50 KB, the overhead is a few milliseconds. For larger payloads, use `max_depth` to limit how deep snapfix serializes nested objects.

**Is it safe to leave `@capture` in the codebase long-term?**
Yes, if `SNAPFIX_ENABLED=false` is set in all non-development environments. The decorator becomes a zero-overhead no-op with that variable set.

**Do I need to set anything up in my test files?**
No. After install, snapfix registers itself with pytest automatically. Generated fixture files are discovered and made available to all tests without any imports or changes to `conftest.py` (the file pytest uses to share fixtures and configuration across a test suite).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for full scope rules, development setup, and PR requirements.

**TL;DR:**

```bash
git clone https://github.com/hacky1997/snapfix
cd snapfix
pip install -e ".[dev]"
pytest --tb=short -q
ruff check src/
```

snapfix has a deliberately narrow scope: capture Python objects, strip PII by field name, emit `@pytest.fixture` files. PRs that expand this scope will be declined. If you have an idea that goes beyond this, open a discussion before writing code.

---

## License

MIT — see [LICENSE](LICENSE).
