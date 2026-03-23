"""
snapfix.diff — snapshot diffing between fixture captures.

Tracks the serialized structure of each capture (not the source code) and
produces human-readable diffs when the structure changes between captures.
"""
from __future__ import annotations

import difflib
import json
import pathlib
from typing import Any, Optional


def _flatten(obj: Any, prefix: str = "") -> dict[str, str]:
    """
    Recursively flatten a serialized dict/list into a mapping of
    dot-notation key paths → repr(value).

    Example:
      {"user": {"email": "***SCRUBBED***"}}
      → {"user.email": "'***SCRUBBED***'"}

    This representation powers structural diffs that ignore irrelevant
    whitespace and focus on actual field-level changes.
    """
    out: dict[str, str] = {}

    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                out.update(_flatten(v, path))
            else:
                out[path] = repr(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                out.update(_flatten(v, path))
            else:
                out[path] = repr(v)
    else:
        out[prefix] = repr(obj)

    return out


def _serialized_lines(data: Any) -> list[str]:
    """Return a stable, sorted list of 'key.path: value' lines for diffing."""
    flat = _flatten(data)
    return sorted(f"{k}: {v}" for k, v in flat.items())


def structural_diff(old_data: Any, new_data: Any, name: str = "fixture") -> str:
    """
    Produce a unified diff between two serialized objects at the
    structural (field path) level.

    Returns an empty string if there is no difference.
    """
    old_lines = _serialized_lines(old_data)
    new_lines = _serialized_lines(new_data)

    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{name} (previous)",
        tofile=f"{name} (current)",
        lineterm="",
        n=3,
    ))

    return "\n".join(diff)


def source_diff(old_source: str, new_source: str, name: str = "fixture") -> str:
    """
    Produce a unified diff between two fixture source files (the generated
    Python). Used by `snapfix diff --source`.
    """
    diff = list(difflib.unified_diff(
        old_source.splitlines(),
        new_source.splitlines(),
        fromfile=f"{name} (previous)",
        tofile=f"{name} (current)",
        lineterm="",
        n=3,
    ))
    return "\n".join(diff)


class SnapfixSnapshot:
    """
    Manages the snapshot store used by `snapfix diff`.

    Each fixture has a snapshot file at:
      {output_dir}/.snapshots/{name}.json

    The snapshot stores the previously captured serialized data,
    not the source code. This allows structural comparison independent
    of formatting changes.
    """

    def __init__(self, output_dir: pathlib.Path):
        self._dir = pathlib.Path(output_dir) / ".snapshots"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> pathlib.Path:
        safe = name.replace(" ", "_").replace("/", "_")
        return self._dir / f"{safe}.json"

    def has(self, name: str) -> bool:
        return self._path(name).exists()

    def load(self, name: str) -> Any:
        p = self._path(name)
        if not p.exists():
            raise FileNotFoundError(f"No snapshot for fixture '{name}'")
        return json.loads(p.read_text())

    def save(self, name: str, data: Any) -> None:
        """Atomically save the serialized data as a snapshot.

        If a previous snapshot exists, it is rotated to .prev.json so that
        'snapfix diff' can compare the last two captures.
        """
        p    = self._path(name)
        prev = p.with_suffix(".prev.json")

        # Rotate existing snapshot → .prev.json before overwriting
        if p.exists():
            import shutil
            shutil.copy2(p, prev)

        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str, sort_keys=True, indent=2))
        tmp.replace(p)

    def delete(self, name: str) -> bool:
        p = self._path(name)
        if p.exists():
            p.unlink()
            return True
        return False

    def list_names(self) -> list[str]:
        return [p.stem for p in sorted(self._dir.glob("*.json"))]
