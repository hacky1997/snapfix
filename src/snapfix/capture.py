from __future__ import annotations

import asyncio
import datetime
import functools
import pathlib
import warnings
from collections.abc import Callable

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
        yaml_path = pathlib.Path("snapfix.yaml")
        _default_config = SnapfixConfig.from_yaml(yaml_path)
    return _default_config


def capture(
    name: str,
    scrub: list[str] | None = None,
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
                _record(name, result, scrub, max_depth, max_size_bytes, config)
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                _record(name, result, scrub, max_depth, max_size_bytes, config)
                return result
            return sync_wrapper
    return decorator


def _record(name, obj, extra_scrub, max_depth, max_size_bytes, cfg_override):
    cfg = _get_config(cfg_override)
    if not cfg.enabled:
        return
    effective_depth = max_depth if max_depth is not None else cfg.max_depth
    effective_size  = max_size_bytes if max_size_bytes is not None else cfg.max_size_bytes
    scrub_fields = list(cfg.default_scrub_fields)
    if extra_scrub:
        scrub_fields = list(set(scrub_fields) | set(extra_scrub))

    serializer = SnapfixSerializer(max_depth=effective_depth, max_size_bytes=effective_size)
    scrubber   = SnapfixScrubber(scrub_fields)
    codegen    = SnapfixCodegen()
    store      = SnapfixStore(cfg.output_dir)

    try:
        serialized = serializer.serialize(obj)
        scrubbed, scrubbed_keys = scrubber.scrub(serialized)
        source = codegen.generate(
            name=name,
            data=scrubbed,
            scrubbed_fields=scrubbed_keys,
            captured_at=datetime.datetime.utcnow(),
        )
        store.write(name, source, {
            "scrubbed_fields": scrubbed_keys,
            "captured_at": str(datetime.datetime.utcnow()),
        })
    except Exception as e:
        warnings.warn(f"snapfix: failed to capture '{name}': {e}", stacklevel=3)
