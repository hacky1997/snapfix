---
title: "How to test your Stripe integration in pytest without committing customer data"
description: "A complete guide to writing reliable Stripe tests using real API responses — safely."
date: 2026-03-24
tags: [python, pytest, stripe, testing, pii]
canonical: https://your-domain.com/blog/stripe-pytest-fixtures
---

# How to Test Your Stripe Integration in pytest Without Committing Customer Data

Every developer who has built a Stripe integration has written some version of this fixture:

```python
@pytest.fixture
def fake_invoice():
    return {
        "id":     "in_test_abc123",
        "status": "paid",
        "amount": 14999,          # is this cents or dollars?
        "customer": {
            "email": "alice@example.com",   # ← is this actually how Stripe nests this?
            "name":  "Alice Smith",
        },
        "lines": {
            "data": [
                {"description": "Pro plan", "amount": 14999}
            ]
        }
    }
```

And every developer who has done this has had at least one of these happen:

- A test that passed with fake data but failed in production because the real Stripe response has `amount_due`, not `amount`
- A fixture that silently used `float` for the amount, when Stripe actually uses integer cents — and the discrepancy only showed up in edge cases involving currency conversion
- A fixture that was "copied from the Stripe docs" and therefore reflected the documented schema, not the actual schema returned by the version of their API tier

There is a better way.

---

## The Problem With Hand-Written Stripe Fixtures

Stripe's API responses are significantly more complex than the documentation examples suggest. A real invoice response includes:

- `amount_due`, `amount_paid`, `amount_remaining` — three separate amount fields, all in integer cents
- `customer` as a string ID or an expanded customer object (depending on your expand parameters)
- `discount` as null or a nested discount object that appears inconsistently
- `metadata` as an arbitrary dict with your custom key–value pairs, which often contains things you did not realize were sensitive
- `lines.data` as a paginated list with its own `object`, `has_more`, `url`, and `total_count` fields

Hand-writing a fixture that accurately reflects all of this — including the edge cases that only appear in your specific account configuration — is not practical. You will always miss something.

---

## The Real Danger: PII In Your Git History

The more immediate problem is not correctness — it is safety.

When a developer needs to fix a failing Stripe integration, the fastest path is to print a real API response and use it as a fixture. This happens on every team. The result is test fixture files that contain real customer emails, billing addresses, and metadata from your Stripe account committed to your git repository.

**This is not a hypothetical risk.** GitHub reported over 39 million leaked secrets across repositories in 2024. Stripe API keys and customer PII are among the most commonly leaked credentials because they travel through exactly this path: production API → developer debugging session → test fixture → git commit → public or semi-public repository.

`git history` does not forget. Even if you delete the file in a later commit, the data is in the history permanently unless you run `git filter-branch` or `BFG Repo-Cleaner` — a complex, disruptive operation that most teams never do.

---

## A Better Approach: Capture Real Responses, Scrub Automatically

The correct workflow is:

1. Call the real Stripe API once in development or staging
2. Capture the exact response, including all the fields you did not know existed
3. Remove every sensitive field automatically — `customer.email`, `customer.address`, `metadata.*`, etc.
4. Write the result as a human-readable, committable test fixture

This is exactly what `snapfix` does.

```bash
pip install snapfix
```

### Step 1: Add the decorator

```python
# myapp/billing.py
from snapfix import capture

@capture(
    "stripe_invoice_paid",
    scrub=["metadata"]          # scrub your custom metadata fields
)
async def fetch_invoice(invoice_id: str) -> dict:
    invoice = await stripe.Invoice.retrieve(
        invoice_id,
        expand=["customer", "lines.data"],
    )
    return invoice.to_dict()
```

The `scrub=["metadata"]` argument adds `metadata` to the default list of scrubbed fields. The default list already includes `email`, `address`, `phone`, `token`, and 18 other patterns. You only need to add fields specific to your application.

### Step 2: Call the function once in development

```bash
# In your development environment or staging
python -c "
import asyncio
from myapp.billing import fetch_invoice
asyncio.run(fetch_invoice('in_1OkRealInvoiceId'))
"
```

You will see this in your terminal:

```
  snapfix ✓  fixture written: tests/fixtures/snapfix_stripe_invoice_paid.py
  snapfix    scrubbed: customer.email, customer.address, metadata.internal_ref
  snapfix    review before committing — value-level PII is not detected
```

### Step 3: Review the generated fixture

Open `tests/fixtures/snapfix_stripe_invoice_paid.py`:

```python
# Generated by snapfix — do not edit manually
# Regenerate  : re-run the @snapfix.capture decorated function
# Captured    : 2026-03-24T14:22:01
# Source      : myapp.billing.fetch_invoice (myapp/billing.py)
# Scrubbed    : customer.email, customer.address, customer.phone,
#               metadata.internal_ref, metadata.customer_crm_id
#
# ⚠  Review before committing: value-level PII is not detected.
#    All scrubbed fields are listed above.
import pytest
from snapfix import reconstruct

@pytest.fixture
def stripe_invoice_paid():
    return reconstruct({
        'id': 'in_1OkRealInvoiceId',
        'object': 'invoice',
        'amount_due': 14999,
        'amount_paid': 14999,
        'amount_remaining': 0,
        'currency': 'usd',
        'status': 'paid',
        'customer': 'cus_PFakeCustomerId',
        'customer_email': '***SCRUBBED***',                           # email
        'customer_address': '***SCRUBBED***',                         # address
        'created': {'__snapfix_type__': 'datetime', 'value': '2026-03-01T09:00:00'},  # datetime
        'lines': {
            'object': 'list',
            'data': [
                {
                    'id': 'il_LineItemId',
                    'object': 'line_item',
                    'amount': 14999,
                    'description': 'Pro plan (March 2026)',
                    'currency': 'usd',
                }
            ],
            'has_more': False,
            'total_count': 1,
        },
        'metadata': '***SCRUBBED***',
        'discount': None,
        'subscription': 'sub_SubscriptionId',
    })
```

**Review this file before committing.** The `# Scrubbed:` header lists every field that was automatically removed. Verify it matches what you expected to be removed.

### Step 4: Remove the decorator

Once the fixture is committed, remove `@capture` from your function. The fixture file lives in your test suite and keeps working without it.

```python
# myapp/billing.py
# No @capture decorator — back to normal

async def fetch_invoice(invoice_id: str) -> dict:
    invoice = await stripe.Invoice.retrieve(
        invoice_id,
        expand=["customer", "lines.data"],
    )
    return invoice.to_dict()
```

### Step 5: Write your tests

```python
# tests/test_billing.py
from decimal import Decimal
import datetime

def test_invoice_is_paid(stripe_invoice_paid):
    assert stripe_invoice_paid["status"] == "paid"

def test_invoice_amount_in_cents(stripe_invoice_paid):
    # Stripe amounts are always integer cents — this is exactly what
    # the captured fixture shows, not what we guessed
    assert stripe_invoice_paid["amount_paid"] == 14999
    assert isinstance(stripe_invoice_paid["amount_paid"], int)

def test_invoice_has_line_items(stripe_invoice_paid):
    lines = stripe_invoice_paid["lines"]["data"]
    assert len(lines) > 0
    assert lines[0]["description"] == "Pro plan (March 2026)"

def test_invoice_customer_pii_is_scrubbed(stripe_invoice_paid):
    # Confirm scrubbing worked — this test documents your compliance behaviour
    assert stripe_invoice_paid["customer_email"] == "***SCRUBBED***"
    assert stripe_invoice_paid["metadata"]        == "***SCRUBBED***"

def test_invoice_created_is_datetime(stripe_invoice_paid):
    # reconstruct() restores the datetime type — not a string, not a timestamp
    assert isinstance(stripe_invoice_paid["created"], datetime.datetime)
```

---

## Running the Pre-Commit PII Audit

Snapfix includes a second line of defence: a PII scanner that checks fixture files for common patterns that might have been missed.

Add this to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: snapfix-audit
        name: snapfix PII audit
        entry: snapfix audit --strict
        language: system
        files: ^tests/fixtures/snapfix_.*\.py$
```

Or run it manually any time:

```bash
snapfix audit

# snapfix audit — tests/fixtures/
# ────────────────────────────────────────────────────────────
#   Files scanned : 8
#   Findings      : 0
#   Status        : ✓ PASSED — no PII patterns detected
```

If it finds something:

```bash
# ✗ FAILED — potential PII detected
#   snapfix_stripe_invoice_paid.py:
#     line  23  [email]
#            'contact_info': 'alice@acmecorp.com',
#
#   To fix: re-capture with @capture(name, scrub=['contact_info'])
```

---

## Keeping Fixtures Up to Date: Detecting API Changes

Stripe occasionally adds new fields to responses, removes deprecated ones, or changes types between API versions. Your hand-written fixtures would never catch this. Snapfix's snapshot diffing does.

```bash
# Re-capture the invoice after upgrading your Stripe API version
# snapfix automatically compares to the previous capture

snapfix diff stripe_invoice_paid

# ✗  Changes detected in 'stripe_invoice_paid':
# --- stripe_invoice_paid (previous)
# +++ stripe_invoice_paid (current)
# @@ -1,3 +1,4 @@
#  lines.data[0].amount: 14999
# +lines.data[0].amount_excluding_tax: 14999
# +lines.data[0].tax_amounts: []
```

Stripe added two new fields in a recent API version. Your snapshot diff caught it. Your CI fails. You update your tests before this reaches production.

---

## Verifying Your Fixture Library

When you have accumulated 20+ fixture files, this command confirms they all work:

```bash
snapfix verify

# snapfix verify — tests/fixtures/
# ────────────────────────────────────────────────────────────
#   ✓  snapfix_stripe_invoice_paid.py  [stripe_invoice_paid]
#   ✓  snapfix_stripe_subscription.py  [stripe_subscription]
#   ✓  snapfix_stripe_webhook_event.py [stripe_webhook_event]
#   ─────────────────────────────────────
#   Total   : 3
#   Passed  : 3
#   Status  : ✓ ALL VALID
```

Add this to your CI pipeline alongside `pytest`:

```yaml
# .github/workflows/ci.yml
- run: snapfix verify
- run: pytest
```

---

## Summary

| Old workflow | Snapfix workflow |
|---|---|
| Hand-write fixture from Stripe docs | Capture from real Stripe response |
| Manually remove PII fields | Automatic field-name scrubbing |
| Hope you got the types right | `reconstruct()` restores `datetime`, `Decimal`, etc. |
| Miss the `discount` edge case | Real data includes every field variant |
| No audit trail for scrubbing | `# Scrubbed:` header in every fixture |
| Never detect Stripe API changes | `snapfix diff` catches schema changes |

```bash
pip install snapfix
```

Add `@capture` to your Stripe endpoint. Call it once in development. Review the fixture. Commit.

The test that would have caught that production incident is three minutes away.

---

*Built with snapfix v0.3.1 — [github.com/hacky1997/snapfix](https://github.com/hacky1997/snapfix)*
