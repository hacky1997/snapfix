# Changelog

All notable changes to snapfix are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
snapfix uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

---

## [0.1.0] — 2026-03-23

### Added
- `@capture` decorator — captures return values of sync and async functions
- `reconstruct()` — restores `__snapfix_type__` markers to Python types
- `SnapfixConfig` — config dataclass with env var and YAML override hierarchy
- `SnapfixSerializer` — recursive serializer supporting 15 Python types:
  `datetime`, `date`, `time`, `timedelta`, `UUID`, `Decimal`, `bytes`,
  `bytearray`, `Path`, `Enum`, `set`, `frozenset`, `tuple`, `dataclass`,
  pydantic v1/v2 `BaseModel`
- Circular reference detection — emits `__snapfix_circular__` sentinel
- Max depth guard — emits `__snapfix_maxdepth__` sentinel at `max_depth`
- Max size guard — emits `__snapfix_truncated__` sentinel above `max_size_bytes`
- Unserializable type fallback — emits `__snapfix_unserializable__` sentinel
- `SnapfixScrubber` — recursive field-name-based PII scrubber (case-insensitive
  substring matching, 22 default field patterns, no input mutation)
- `SnapfixCodegen` — generates valid `@pytest.fixture` Python source
- `SnapfixStore` — atomic fixture file writes with `.snapfix_index.json`
- CLI: `snapfix list`, `snapfix show`, `snapfix clear`, `snapfix clear-all`
- `snapfix.yaml` project-level configuration support
- `SNAPFIX_ENABLED`, `SNAPFIX_OUTPUT_DIR`, `SNAPFIX_MAX_DEPTH`,
  `SNAPFIX_MAX_SIZE` environment variable overrides

### Documented limitations
- Field-name scrubbing only: PII in field values is not detected
- `tuple` → `list` on roundtrip (JSON has no tuple type)
- Enum class is not preserved on roundtrip, only `.value`
- Objects without `__dict__`, `.model_dump()`, or `.dict()` emit the
  `__snapfix_unserializable__` sentinel

[Unreleased]: https://github.com/yourname/snapfix/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourname/snapfix/releases/tag/v0.1.0
