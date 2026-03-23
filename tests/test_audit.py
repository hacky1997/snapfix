"""
Tests for snapfix.audit — PII value-level scanner.
"""
import pathlib
import pytest
from snapfix.audit import scan_file, scan_directory, AuditResult, Finding, format_report


def _write_fixture(tmp_path: pathlib.Path, name: str, content: str) -> pathlib.Path:
    p = tmp_path / f"snapfix_{name}.py"
    p.write_text(content)
    return p


# ── scan_file: clean fixtures ─────────────────────────────────────────────────

def test_clean_fixture_no_findings(tmp_path):
    f = _write_fixture(tmp_path, "clean", """
import pytest
from snapfix import reconstruct

@pytest.fixture
def clean():
    return reconstruct({
        'id': 'INV-001',
        'email': '***SCRUBBED***',
        'plan': 'pro',
        'amount': {'__snapfix_type__': 'decimal', 'value': '149.99'},
    })
""")
    findings = scan_file(f)
    assert findings == [], f"Expected no findings, got: {findings}"


def test_scrubbed_values_not_flagged(tmp_path):
    f = _write_fixture(tmp_path, "scrubbed", """
@pytest.fixture
def scrubbed():
    return {'email': '***SCRUBBED***', 'token': '***SCRUBBED***'}
""")
    assert scan_file(f) == []


def test_comment_lines_not_scanned(tmp_path):
    f = _write_fixture(tmp_path, "comment", """
# Scrubbed: alice@example.com, 555-867-5309
# This is a comment line — should not be flagged
@pytest.fixture
def fixture():
    return {'plan': 'pro'}
""")
    assert scan_file(f) == []


def test_example_domain_not_flagged(tmp_path):
    """Addresses at example.com are test data by convention."""
    f = _write_fixture(tmp_path, "example", """
@pytest.fixture
def fixture():
    return {'contact': 'test@example.com'}
""")
    assert scan_file(f) == []


# ── scan_file: PII detection ──────────────────────────────────────────────────

def test_real_email_detected(tmp_path):
    f = _write_fixture(tmp_path, "leaked_email", """
@pytest.fixture
def fixture():
    return {'contact': 'alice@acmecorp.com', 'plan': 'pro'}
""")
    findings = scan_file(f)
    assert any(g.pattern == "email" for g in findings)


def test_phone_number_detected(tmp_path):
    f = _write_fixture(tmp_path, "leaked_phone", """
@pytest.fixture
def fixture():
    return {'contact': '555-867-5309', 'plan': 'pro'}
""")
    findings = scan_file(f)
    assert any(g.pattern == "phone" for g in findings)


def test_credit_card_detected(tmp_path):
    f = _write_fixture(tmp_path, "leaked_cc", """
@pytest.fixture
def fixture():
    return {'card': '4111111111111111'}
""")
    findings = scan_file(f)
    assert any(g.pattern == "credit_card" for g in findings)


def test_finding_has_line_number(tmp_path):
    f = _write_fixture(tmp_path, "lineno", """
@pytest.fixture
def fixture():
    return {
        'plan': 'pro',
        'email': 'real@company.com',
    }
""")
    findings = scan_file(f)
    email_findings = [g for g in findings if g.pattern == "email"]
    assert email_findings
    assert email_findings[0].line_number > 0


def test_finding_does_not_expose_full_match_in_str(tmp_path):
    """str(Finding) should redact the matched value."""
    f = _write_fixture(tmp_path, "redact", """
@pytest.fixture
def f():
    return {'e': 'alice@acmecorp.com'}
""")
    findings = scan_file(f)
    assert findings
    displayed = str(findings[0])
    assert "alice@acmecorp.com" not in displayed
    assert "***" in displayed


# ── scan_directory ────────────────────────────────────────────────────────────

def test_scan_directory_counts_files(tmp_path):
    for name in ["a", "b", "c"]:
        _write_fixture(tmp_path, name, "@pytest.fixture\ndef f(): return {'x': 1}")
    result = scan_directory(tmp_path)
    assert result.files_scanned == 3


def test_scan_directory_passed_when_clean(tmp_path):
    _write_fixture(tmp_path, "clean", "@pytest.fixture\ndef f(): return {'x': 1}")
    result = scan_directory(tmp_path)
    assert result.passed


def test_scan_directory_failed_when_pii(tmp_path):
    _write_fixture(tmp_path, "pii", "@pytest.fixture\ndef f(): return {'e': 'real@corp.com'}")
    result = scan_directory(tmp_path)
    assert not result.passed
    assert result.finding_count > 0


def test_scan_directory_empty(tmp_path):
    result = scan_directory(tmp_path)
    assert result.files_scanned == 0
    assert result.passed


def test_audit_result_dataclass():
    r = AuditResult(files_scanned=3, findings=[], passed=True)
    assert r.finding_count == 0
    assert r.passed


# ── format_report ─────────────────────────────────────────────────────────────

def test_format_report_passed(tmp_path):
    result = AuditResult(files_scanned=2, findings=[], passed=True)
    report = format_report(result, tmp_path)
    assert "PASSED" in report
    assert "2" in report


def test_format_report_failed(tmp_path):
    finding = Finding(
        file=tmp_path / "snapfix_x.py",
        line_number=5,
        line="    'email': 'real@corp.com',",
        pattern="email",
        match="real@corp.com",
    )
    result = AuditResult(files_scanned=1, findings=[finding], passed=False)
    report = format_report(result, tmp_path)
    assert "FAILED" in report
    assert "email" in report


def test_format_report_remediation_hint(tmp_path):
    finding = Finding(
        file=tmp_path / "snapfix_x.py",
        line_number=5,
        line="    'email': 'real@corp.com',",
        pattern="email",
        match="real@corp.com",
    )
    result = AuditResult(files_scanned=1, findings=[finding], passed=False)
    report = format_report(result, tmp_path)
    assert "scrub" in report.lower() or "SCRUBBED" in report
