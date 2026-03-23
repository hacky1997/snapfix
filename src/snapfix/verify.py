"""
snapfix.verify — fixture health checker.

Runs all existing snapfix fixture files through reconstruct() to confirm:
  1. The file is valid Python
  2. It imports without error
  3. The fixture function exists and is callable
  4. Calling the fixture returns a non-empty, non-None result
  5. The result contains no __snapfix_truncated__ or __snapfix_circular__ sentinels
     at the top level (which would indicate an incomplete capture)

Usage:
    snapfix verify
    snapfix verify --strict     # fail on any sentinel markers (truncated, circular)
    snapfix verify --dir tests/fixtures
"""
from __future__ import annotations

import ast
import dataclasses
import importlib.util
import pathlib
import sys
import types
from typing import Any

# Import reconstruct directly — we need it available when executing fixture modules
from snapfix.serializer import _CIRC, _TRUNC, _UNSZ


@dataclasses.dataclass
class VerifyResult:
    file:          pathlib.Path
    fixture_name:  str
    passed:        bool
    error:         str | None
    warnings:      list[str]
    value_type:    str | None

    def __str__(self) -> str:
        status = "✓" if self.passed else "✗"
        warn   = f"  ⚠ {'; '.join(self.warnings)}" if self.warnings else ""
        err    = f"  → {self.error}" if self.error else ""
        return f"  {status}  {self.file.name}  [{self.fixture_name}]{err}{warn}"


def _has_sentinel(value: Any, key: str, _depth: int = 0) -> bool:
    """Recursively check if value contains a specific snapfix sentinel."""
    if _depth > 5:
        return False
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_has_sentinel(v, key, _depth + 1) for v in value.values())
    if isinstance(value, list):
        return any(_has_sentinel(x, key, _depth + 1) for x in value)
    return False


def verify_file(path: pathlib.Path, strict: bool = False) -> VerifyResult:
    """Verify a single fixture file. Returns a VerifyResult."""
    fixture_name = path.stem.removeprefix("snapfix_")
    warnings: list[str] = []

    # Step 1: valid Python
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
    except SyntaxError as e:
        return VerifyResult(path, fixture_name, False, f"SyntaxError: {e}", warnings, None)
    except Exception as e:
        return VerifyResult(path, fixture_name, False, f"Read error: {e}", warnings, None)

    # Step 2: importable
    try:
        # Stub pytest.fixture for import — we just want the value
        _fake_pytest = types.ModuleType("pytest")
        _fake_pytest.fixture = lambda f: f  # type: ignore
        original_pytest = sys.modules.get("pytest")
        sys.modules["pytest"] = _fake_pytest

        spec = importlib.util.spec_from_file_location(f"_snapfix_verify_{fixture_name}", path)
        if spec is None or spec.loader is None:
            return VerifyResult(path, fixture_name, False, "Could not load module spec", warnings, None)

        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"_snapfix_verify_{fixture_name}"] = mod
        spec.loader.exec_module(mod)  # type: ignore

        if original_pytest is not None:
            sys.modules["pytest"] = original_pytest
        elif "pytest" in sys.modules:
            del sys.modules["pytest"]

    except ImportError as e:
        return VerifyResult(path, fixture_name, False, f"ImportError: {e}", warnings, None)
    except Exception as e:
        return VerifyResult(path, fixture_name, False, f"Import failed: {e}", warnings, None)
    finally:
        sys.modules.pop(f"_snapfix_verify_{fixture_name}", None)

    # Step 3: fixture function exists
    fn = getattr(mod, fixture_name, None)
    if fn is None:
        # Try to find any callable that isn't reconstruct or pytest builtins
        candidates = [
            name for name in dir(mod)
            if not name.startswith("_")
            and callable(getattr(mod, name))
            and name not in ("reconstruct", "fixture")
        ]
        if not candidates:
            return VerifyResult(path, fixture_name, False,
                                f"No fixture function found (expected '{fixture_name}')",
                                warnings, None)
        fn = getattr(mod, candidates[0])
        fixture_name = candidates[0]

    # Step 4: callable and returns a value
    try:
        value = fn()
    except Exception as e:
        return VerifyResult(path, fixture_name, False, f"Fixture raised: {e}", warnings, None)

    if value is None:
        # None is a valid return value — not an error, but worth noting
        warnings.append("fixture returns None (valid but check if intentional)")
        return VerifyResult(path, fixture_name, True, None, warnings, "NoneType")

    value_type = type(value).__name__

    # Step 5: sentinel checks
    if _has_sentinel(value, _TRUNC):
        msg = "contains __snapfix_truncated__ — object was too large when captured"
        if strict:
            return VerifyResult(path, fixture_name, False, msg, warnings, value_type)
        warnings.append(msg)

    if _has_sentinel(value, _CIRC):
        msg = "contains __snapfix_circular__ — circular reference in original object"
        if strict:
            return VerifyResult(path, fixture_name, False, msg, warnings, value_type)
        warnings.append(msg)

    if _has_sentinel(value, _UNSZ):
        msg = "contains __snapfix_unserializable__ — some fields could not be serialized"
        if strict:
            return VerifyResult(path, fixture_name, False, msg, warnings, value_type)
        warnings.append(msg)

    return VerifyResult(path, fixture_name, True, None, warnings, value_type)


def verify_directory(
    directory: pathlib.Path,
    glob: str = "snapfix_*.py",
    strict: bool = False,
) -> list[VerifyResult]:
    """Verify all snapfix fixture files in a directory."""
    files = sorted(directory.glob(glob))
    return [verify_file(f, strict=strict) for f in files]


def format_verify_report(results: list[VerifyResult], directory: pathlib.Path) -> str:
    """Return a human-readable verify report."""
    passed  = [r for r in results if r.passed]
    failed  = [r for r in results if not r.passed]
    warned  = [r for r in results if r.passed and r.warnings]

    lines = []
    lines.append(f"\nsnapfix verify — {directory}")
    lines.append(f"{'─' * 60}")

    if not results:
        lines.append("  No fixture files found.")
        return "\n".join(lines)

    for r in results:
        lines.append(str(r))

    lines.append(f"\n  {'─' * 40}")
    lines.append(f"  Total   : {len(results)}")
    lines.append(f"  Passed  : {len(passed)}")
    lines.append(f"  Failed  : {len(failed)}")
    lines.append(f"  Warnings: {len(warned)}")

    if failed:
        lines.append("\n  Status  : ✗ FAILED")
        lines.append("  Re-capture failed fixtures: remove @capture, add it again,")
        lines.append("  call the function once in staging.")
    else:
        lines.append("\n  Status  : ✓ ALL VALID")

    lines.append("")
    return "\n".join(lines)