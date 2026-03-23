from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Dict, List, Optional

from snapfix.diff import SnapfixSnapshot, structural_diff, source_diff


class SnapfixStore:
    def __init__(self, output_dir: pathlib.Path):
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.output_dir / ".snapfix_index.json"
        self._snapshots  = SnapfixSnapshot(self.output_dir)

    # ── Index I/O ─────────────────────────────────────────────────────────────

    def _load_index(self) -> Dict:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text())
            except Exception:
                return {}
        return {}

    def _save_index(self, idx: Dict) -> None:
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, indent=2, default=str))
        tmp.replace(self._index_path)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def write(
        self,
        name: str,
        source: str,
        metadata: Dict[str, Any],
        serialized_data: Optional[Any] = None,
    ) -> pathlib.Path:
        """Write fixture source + update snapshot if serialized_data provided."""
        safe = _sanitize(name)
        path = self.output_dir / f"snapfix_{safe}.py"
        tmp  = path.with_suffix(".tmp")
        tmp.write_text(source, encoding="utf-8")
        tmp.replace(path)

        # Save snapshot for diffing
        if serialized_data is not None:
            self._snapshots.save(name, serialized_data)

        idx = self._load_index()
        idx[name] = {"path": str(path), "has_snapshot": serialized_data is not None, **metadata}
        self._save_index(idx)
        return path

    def list(self) -> List[Dict]:
        return list(self._load_index().values())

    def exists(self, name: str) -> bool:
        return name in self._load_index()

    def delete(self, name: str) -> bool:
        idx   = self._load_index()
        entry = idx.pop(name, None)
        if entry:
            p = pathlib.Path(entry["path"])
            if p.exists():
                p.unlink()
            self._snapshots.delete(name)
        self._save_index(idx)
        return entry is not None

    # ── Diff support ──────────────────────────────────────────────────────────

    def diff(self, name: str, new_data: Any, mode: str = "structural") -> str:
        """
        Compare new_data against the stored snapshot for `name`.

        mode="structural" — field-path level diff (recommended)
        mode="source"     — raw source file diff

        Returns empty string if no diff or no previous snapshot.
        """
        if not self._snapshots.has(name):
            return ""

        old_data = self._snapshots.load(name)

        if mode == "source":
            idx   = self._load_index()
            entry = idx.get(name, {})
            p     = pathlib.Path(entry.get("path", ""))
            if p.exists():
                old_source = p.read_text()
                return source_diff(old_source, "", name)
            return ""

        return structural_diff(old_data, new_data, name)

    def has_snapshot(self, name: str) -> bool:
        return self._snapshots.has(name)

    def snapshot_names(self) -> List[str]:
        return self._snapshots.list_names()


def _sanitize(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return ("_" + s) if s and s[0].isdigit() else s or "_unnamed"
