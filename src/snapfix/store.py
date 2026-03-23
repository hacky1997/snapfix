from __future__ import annotations
import json
import pathlib
import re
from typing import Any, Dict, List


class SnapfixStore:
    def __init__(self, output_dir: pathlib.Path):
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.output_dir / ".snapfix_index.json"

    def _load_index(self) -> Dict:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text())
            except Exception:
                return {}
        return {}

    def _save_index(self, idx: Dict):
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, indent=2, default=str))
        tmp.replace(self._index_path)

    def write(self, name: str, source: str, metadata: Dict[str, Any]) -> pathlib.Path:
        safe = _sanitize(name)
        path = self.output_dir / f"snapfix_{safe}.py"
        tmp  = path.with_suffix(".tmp")
        tmp.write_text(source, encoding="utf-8")
        tmp.replace(path)
        idx = self._load_index()
        idx[name] = {"path": str(path), **metadata}
        self._save_index(idx)
        return path

    def list(self) -> List[Dict]:
        return list(self._load_index().values())

    def exists(self, name: str) -> bool:
        return name in self._load_index()

    def delete(self, name: str) -> bool:
        idx = self._load_index()
        entry = idx.pop(name, None)
        if entry and pathlib.Path(entry["path"]).exists():
            pathlib.Path(entry["path"]).unlink()
        self._save_index(idx)
        return entry is not None


def _sanitize(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return ("_" + s) if s and s[0].isdigit() else s or "_unnamed"
