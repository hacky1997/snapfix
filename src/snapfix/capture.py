from __future__ import annotations

import asyncio
import datetime
import functools
import pathlib
import sys
from typing import Any, Callable, List
import warnings

from snapfix.codegen import SnapfixCodegen
from snapfix.config import SnapfixConfig
from snapfix.scrubber import SnapfixScrubber
from snapfix.serializer import SnapfixSerializer
from snapfix.store import SnapfixStore

_default_config: SnapfixConfig | None = None


def _get_config(cfg: SnapfixConfig | None) -> SnapfixConfig:
    global _default_config
    if cfg is not None:
        return cfg
    if _default_config is None:
        _default_config = SnapfixConfig.from_yaml(pathlib.Path("snapfix.yaml"))
    return _default_config


def capture(
    name: str,
    scrub: List[str] | None = None,
    max_depth: int | None = None,
    max_size_bytes: int | None = None,
    config: SnapfixConfig | None = None,
) -> Callable:
    """Decorator: capture function return value and emit a pytest fixture."""
    def decorator(fn: Callable) -> Callable:
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                _record(name, result, scrub, max_depth, max_size_bytes, config, fn)
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                _record(name, result, scrub, max_depth, max_size_bytes, config, fn)
                return result
            return sync_wrapper
    return decorator


def _record(
    name: str,
    obj: Any,
    extra_scrub: List[str] | None,
    max_depth: int | None,
    max_size_bytes: int | None,
    cfg_override: SnapfixConfig | None,
    source_fn: Callable | None = None,
) -> None:
    cfg = _get_config(cfg_override)
    if not cfg.enabled:
        return

    effective_depth = max_depth if max_depth is not None else cfg.max_depth
    effective_size  = max_size_bytes if max_size_bytes is not None else cfg.max_size_bytes
    scrub_fields    = list(cfg.default_scrub_fields)
    if extra_scrub:
        scrub_fields = list(set(scrub_fields) | set(extra_scrub))

    serializer = SnapfixSerializer(max_depth=effective_depth, max_size_bytes=effective_size)
    scrubber   = SnapfixScrubber(scrub_fields)
    codegen    = SnapfixCodegen()

    try:
        store      = SnapfixStore(cfg.output_dir)   # ← now inside try, error is caught
        serialized = serializer.serialize(obj)
        scrubbed, scrubbed_keys = scrubber.scrub(serialized)
        source = codegen.generate(
            name=name,
            data=scrubbed,
            scrubbed_fields=scrubbed_keys,
            captured_at=datetime.datetime.utcnow(),
            source_fn=source_fn,
        )
        path = store.write(name, source, {
            "scrubbed_fields": scrubbed_keys,
            "captured_at":     str(datetime.datetime.utcnow()),
            "source_fn":       f"{source_fn.__module__}.{source_fn.__qualname__}" if source_fn else None,
        }, serialized_data=scrubbed)
        _print_success(name, path, scrubbed_keys)

    except Exception as exc:
        _print_failure(name, exc)


# ── Terminal output helpers ───────────────────────────────────────────────────

def _supports_color() -> bool:
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def _c(text: str, code: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _print_success(name: str, path: pathlib.Path, scrubbed_keys: List[str]) -> None:
    label  = _c("snapfix", "1;36")        # bold cyan
    tick   = _c("✓", "32")                # green
    print(f"\n  {label} {tick}  fixture written: {path}", file=sys.stderr)
    if scrubbed_keys:
        fields = ", ".join(scrubbed_keys[:5])
        extra  = f" (+{len(scrubbed_keys)-5} more)" if len(scrubbed_keys) > 5 else ""
        print(f"  {label}    scrubbed: {_c(fields + extra, '33')}", file=sys.stderr)
    print(f"  {label}    review before committing — value-level PII is not detected\n",
          file=sys.stderr)


def _print_failure(name: str, exc: Exception) -> None:
    label = _c("snapfix", "1;36")
    cross = _c("✗", "31")
    bar   = _c("─" * 60, "31")
    print(f"\n  {label} {cross}  capture FAILED for '{name}'", file=sys.stderr)
    print(f"  {bar}", file=sys.stderr)
    print(f"  {_c('Error:', '31')} {type(exc).__name__}: {exc}", file=sys.stderr)

    hint = _get_hint(exc)
    if hint:
        print(f"  {_c('Hint:', '33')}  {hint}", file=sys.stderr)

    print(f"\n  {_c('The decorated function ran normally — only fixture writing failed.', '2')}",
          file=sys.stderr)
    print(f"  {_c('To debug: set SNAPFIX_ENABLED=false to silence this warning.', '2')}\n",
          file=sys.stderr)

    warnings.warn(
        f"snapfix: failed to capture '{name}': {type(exc).__name__}: {exc}",
        stacklevel=4,
    )


def _get_hint(exc: Exception) -> str:
    msg = str(exc).lower()
    if "max_size" in msg or "truncated" in msg:
        return "Object is too large. Try @capture(..., max_size_bytes=2_000_000) or reduce max_depth."
    if "circular" in msg:
        return "Object contains a circular reference. snapfix handles this — check the output for __snapfix_circular__ markers."
    if "permission" in msg or "errno 13" in msg:
        return f"Cannot write to output directory. Check SNAPFIX_OUTPUT_DIR or snapfix.yaml."
    if "serializ" in msg:
        return "An object type could not be serialized. Check the fixture for __snapfix_unserializable__ markers."
    return "Run with SNAPFIX_ENABLED=false to skip capture and investigate the object manually."