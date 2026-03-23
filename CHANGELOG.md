# Changelog

All notable changes to snapfix are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

---

## [0.3.2] — 2026-03-23

### Fixed — release reliability
- PyPI publish workflow now uses `skip-existing: true` to avoid failing
  re-runs for an already-published artifact.

### Fixed — package lint hygiene
- Applied import/order/newline and typing-hint lint fixes across `src/` so
  `ruff check src` passes consistently in CI.

---

## [0.3.1] — 2026-03-24

### Added — `snapfix audit`
- `snapfix audit` CLI command — scans fixture files for PII value patterns
  that field-name scrubbing may have missed
- Detects: email addresses, US phone numbers, SSNs, credit card numbers
  (Visa/MC/Amex/Discover), AWS access keys, long API key-like strings
- Skips lines that already contain `***SCRUBBED***`, `example.com`,
  `test@`, `placeholder`, `dummy`, or `fake` — minimises false positives
- `--strict` flag: exit code 1 on any finding (pre-commit / CI safe)
- `--quiet` flag: only print findings, no full report
- Pre-commit hook configuration documented in `snapfix audit --help`
- `snapfix.audit.scan_file()` and `scan_directory()` as public API
- `AuditResult` and `Finding` dataclasses for programmatic use

### Added — `snapfix verify`
- `snapfix verify` CLI command — runs all fixture files through
  `reconstruct()` and confirms they import, execute, and return valid data
- Checks: valid Python syntax, importable without errors, fixture function
  callable, returns a non-None result (warning), no sentinel markers
- `--strict` flag: fail on `__snapfix_truncated__`, `__snapfix_circular__`,
  or `__snapfix_unserializable__` markers in fixture return values
- `snapfix.verify.verify_file()` and `verify_directory()` as public API
- `VerifyResult` dataclass for programmatic use
- Add `snapfix verify` to CI alongside `pytest` for full fixture health checks

### Added — pre-commit hook documentation
- `.pre-commit-config.yaml` example for `snapfix audit --strict` in README
  and `snapfix audit --help`

---

## [0.3.0] — 2026-03-24

### Added — pytest plugin
- `snapfix.plugin` registered as a `pytest11` entry point — snapfix is now a
  first-class pytest plugin, no `conftest.py` changes required
- `--snapfix-capture` flag: enable capture for the entire pytest session
- `--no-snapfix-capture` flag: disable capture for the entire pytest session
- `--snapfix-dir PATH` flag: override output directory for the session
- Auto-discovery of `snapfix_*.py` fixture files via `pytest_collect_file` —
  generated fixtures appear in `pytest --collect-only` and `pytest --fixtures`
- `snapfix_store` session-scoped fixture for testing store interactions
- `snapfix_config` session-scoped fixture for testing `@capture` usage
- Auto-disables capture in CI environments unless `--snapfix-capture` is
  explicitly passed — prevents accidental staging traffic in CI

### Added — `snapfix diff` command
- `snapfix diff <name>` — shows structural field-path diff between the last
  two captures of a fixture; exits with code 1 if differences found (CI-safe)
- `snapfix diff <name> --mode source` — shows raw Python source diff
- `snapfix.diff.structural_diff()` — public API for programmatic diffing
- `snapfix.diff.SnapfixSnapshot` — snapshot store for diff state management
- Snapshot rotation: each re-capture rotates previous snapshot to `.prev.json`
- `snapfix snapshots` CLI command — lists all stored snapshots
- `snapfix list` now shows `◉` for fixtures with snapshots, `○` for new ones

### Changed — first-run experience
- Capture success now prints a colored confirmation to stderr with the fixture
  path and list of scrubbed fields
- Capture failure now prints a loud, structured error to stderr with the exact
  exception type, a context-specific hint, and instructions
- `codegen.py`: all `__snapfix_type__` markers now have inline comments
  (e.g., `# datetime`, `# UUID`, `# Decimal`) making generated fixtures
  human-readable without knowing the marker format
- Generated fixture header now includes the source function's fully-qualified
  name and file path
- Capture decorator passes serialized data to store for snapshot tracking

### Fixed
- `pyyaml` added to runtime `dependencies` in `pyproject.toml` (was missing,
  caused `ModuleNotFoundError: No module named 'yaml'` on fresh installs)

---

## [0.1.0] — 2026-03-23

### Added
- `@capture` decorator (sync + async), `reconstruct()`, `SnapfixConfig`
- `SnapfixSerializer` supporting 15 Python types with circular ref / depth /
  size guards and unserializable fallback
- `SnapfixScrubber` — recursive field-name PII scrubber, no input mutation
- `SnapfixCodegen` — generates valid `@pytest.fixture` Python source
- `SnapfixStore` — atomic fixture writes with `.snapfix_index.json`
- CLI: `snapfix list`, `snapfix show`, `snapfix clear`, `snapfix clear-all`
- `snapfix.yaml` project-level config, env var overrides
- `py.typed` PEP 561 marker

### Documented limitations
- Field-name scrubbing only: value-level PII not detected
- `tuple` → `list` on roundtrip (JSON limitation)
- Enum class not preserved on roundtrip

[Unreleased]: https://github.com/hacky1997/snapfix/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/hacky1997/snapfix/compare/v0.1.0...v0.3.0
[0.1.0]: https://github.com/hacky1997/snapfix/releases/tag/v0.1.0
