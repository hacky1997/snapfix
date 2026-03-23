"""
snapfix.audit — PII value-level scanner for generated fixture files.

This is the second line of defence after field-name scrubbing.
It scans fixture file CONTENTS for common PII patterns (email addresses,
phone numbers, SSN-like patterns, credit card patterns) that may have
been missed because they were stored under non-obvious key names.

Usage:
    # As a CLI command:
    snapfix audit

    # As a pre-commit hook (add to .pre-commit-config.yaml):
    - repo: local
      hooks:
        - id: snapfix-audit
          name: snapfix PII audit
          entry: snapfix audit --strict
          language: system
          files: ^tests/fixtures/snapfix_.*\\.py$

    # Programmatically:
    from snapfix.audit import AuditResult, scan_file, scan_directory
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
from typing import List


# ── PII detection patterns ────────────────────────────────────────────────────
# These are deliberately conservative — they only flag high-confidence patterns
# to minimise false positives in test files that may contain example/test data.

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Email addresses — high confidence, low false-positive rate
    (
        "email",
        re.compile(
            r"(?<![A-Za-z0-9._%+\-])"          # not preceded by email chars
            r"[A-Za-z0-9._%+\-]{2,}"            # local part (min 2 chars)
            r"@"
            r"[A-Za-z0-9.\-]{2,}"               # domain
            r"\.[A-Za-z]{2,6}"                  # TLD
            r"(?![A-Za-z0-9._%+\-@])",          # not followed by email chars
        ),
    ),
    # US phone numbers — (555) 867-5309, 555-867-5309, 5558675309
    (
        "phone",
        re.compile(
            r"(?<!\d)"
            r"(\+?1[\s\-.]?)?"                  # optional country code
            r"(\(?\d{3}\)?)"                    # area code
            r"[\s\-.]"
            r"\d{3}"
            r"[\s\-.]"
            r"\d{4}"
            r"(?!\d)",
        ),
    ),
    # SSN — 123-45-6789 or 123456789
    (
        "ssn",
        re.compile(
            r"(?<!\d)"
            r"\d{3}"
            r"[-\s]?"
            r"\d{2}"
            r"[-\s]?"
            r"\d{4}"
            r"(?!\d)",
        ),
    ),
    # Credit card numbers — 4111 1111 1111 1111, 4111111111111111
    (
        "credit_card",
        re.compile(
            r"(?<!\d)"
            r"(?:4[0-9]{12}(?:[0-9]{3})?"       # Visa
            r"|5[1-5][0-9]{14}"                 # Mastercard
            r"|3[47][0-9]{13}"                  # Amex
            r"|6(?:011|5[0-9]{2})[0-9]{12})"    # Discover
            r"(?!\d)",
        ),
    ),
    # AWS-style access keys — AKIA...
    (
        "aws_key",
        re.compile(r"(?<![A-Z0-9])(AKIA|ASIA|AROA)[A-Z0-9]{16}(?![A-Z0-9])"),
    ),
    # Generic API keys / tokens — long alphanum strings in string literals
    # Only flag if they look like real keys (32+ chars, mixed case/digits)
    (
        "api_key",
        re.compile(
            r"['\"]"
            r"(?=[A-Za-z0-9\-_]*[A-Z](?=[A-Za-z0-9\-_]*[0-9])|[A-Za-z0-9\-_]*[0-9](?=[A-Za-z0-9\-_]*[A-Z]))"
            r"[A-Za-z0-9\-_]{32,}"
            r"['\"]",
        ),
    ),
]

# Lines to skip — already scrubbed or clearly test/example data
_SKIP_PATTERNS = re.compile(
    r"\*\*\*SCRUBBED\*\*\*"       # already scrubbed by snapfix
    r"|example\.com"               # test domains
    r"|test@"                      # obvious test emails
    r"|placeholder"
    r"|dummy"
    r"|fake",
    re.IGNORECASE,
)


@dataclasses.dataclass
class Finding:
    file:        pathlib.Path
    line_number: int
    line:        str
    pattern:     str
    match:       str

    def __str__(self) -> str:
        redacted = self.match[:4] + "***" if len(self.match) > 4 else "***"
        safe_line = self.line.replace(self.match, redacted)   # ← scrub match from line
        return (
            f"  {self.file.name}:{self.line_number}  "
            f"[{self.pattern}]  {redacted}  "
            f"— {safe_line.strip()[:80]}"
        )


@dataclasses.dataclass
class AuditResult:
    files_scanned: int
    findings:      List[Finding]
    passed:        bool

    @property
    def finding_count(self) -> int:
        return len(self.findings)


def scan_file(path: pathlib.Path) -> List[Finding]:
    """Scan a single fixture file for PII patterns. Returns list of findings."""
    findings: List[Finding] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return findings

    for lineno, line in enumerate(lines, 1):
        # Skip comments (scrub audit lines, header lines)
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Skip lines that contain known-safe markers
        if _SKIP_PATTERNS.search(line):
            continue

        for pattern_name, pattern in _PATTERNS:
            for match in pattern.finditer(line):
                findings.append(Finding(
                    file=path,
                    line_number=lineno,
                    line=line,
                    pattern=pattern_name,
                    match=match.group(),
                ))

    return findings


def scan_directory(
    directory: pathlib.Path,
    glob: str = "snapfix_*.py",
) -> AuditResult:
    """Scan all snapfix fixture files in a directory."""
    files   = sorted(directory.glob(glob))
    all_findings: List[Finding] = []

    for f in files:
        all_findings.extend(scan_file(f))

    return AuditResult(
        files_scanned=len(files),
        findings=all_findings,
        passed=len(all_findings) == 0,
    )


def format_report(result: AuditResult, directory: pathlib.Path) -> str:
    """Return a human-readable audit report."""
    lines = []
    lines.append(f"\nsnapfix audit — {directory}")
    lines.append(f"{'─' * 60}")
    lines.append(f"  Files scanned : {result.files_scanned}")

    if result.passed:
        lines.append(f"  Findings      : 0")
        lines.append(f"  Status        : ✓ PASSED — no PII patterns detected\n")
        lines.append(
            "  Note: This audit checks for common PII value patterns.\n"
            "  It does not guarantee all PII has been removed.\n"
            "  Always review generated fixtures before committing.\n"
        )
        return "\n".join(lines)

    lines.append(f"  Findings      : {result.finding_count}")
    lines.append(f"  Status        : ✗ FAILED — potential PII detected\n")

    by_file: dict[str, list[Finding]] = {}
    for f in result.findings:
        by_file.setdefault(str(f.file), []).append(f)

    for filepath, file_findings in by_file.items():
        lines.append(f"  {pathlib.Path(filepath).name}:")
        for finding in file_findings:
            lines.append(f"    line {finding.line_number:3d}  [{finding.pattern}]")
            lines.append(f"           {finding.line.strip()[:100]}")
        lines.append("")

    lines.append("  To fix: re-capture with @capture(name, scrub=[<field_name>])")
    lines.append("          or manually replace the value with '***SCRUBBED***'")
    lines.append("")

    return "\n".join(lines)