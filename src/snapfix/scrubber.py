from __future__ import annotations

from typing import Any

_SCRUBBED_STR = "***SCRUBBED***"
_SCRUBBED_NUM = -1


class SnapfixScrubber:
    def __init__(self, fields: list[str], *, numeric_replacement: int = _SCRUBBED_NUM):
        self._fields = [f.lower() for f in fields]
        self._numeric_replacement = numeric_replacement

    def _is_sensitive(self, key: str) -> bool:
        k = str(key).lower()
        return any(f in k for f in self._fields)

    def _scrub_value(self, value: Any) -> Any:
        if isinstance(value, (int, float)):
            return self._numeric_replacement
        return _SCRUBBED_STR

    def scrub(self, data: Any, _scrubbed: list[str] | None = None) -> tuple[Any, list[str]]:
        """Returns (scrubbed_copy, list_of_scrubbed_key_paths).
        Does NOT mutate the input.
        """
        top_level = _scrubbed is None
        if top_level:
            _scrubbed = []
        result = self._scrub_node(data, _scrubbed, path="")
        return result, _scrubbed

    def _scrub_node(self, data: Any, scrubbed: list[str], path: str) -> Any:
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                key_path = f"{path}.{k}" if path else str(k)
                if self._is_sensitive(k):
                    out[k] = self._scrub_value(v)
                    scrubbed.append(key_path)
                else:
                    out[k] = self._scrub_node(v, scrubbed, key_path)
            return out
        if isinstance(data, list):
            return [
                self._scrub_node(item, scrubbed, f"{path}[{i}]")
                for i, item in enumerate(data)
            ]
        return data
