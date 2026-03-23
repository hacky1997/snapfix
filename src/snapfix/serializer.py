from __future__ import annotations
import base64
import dataclasses
import datetime
import decimal
import enum
import json
import math
import pathlib
import uuid
from typing import Any, Optional

_MARKER = "__snapfix_type__"
_UNSZ   = "__snapfix_unserializable__"
_CIRC   = "__snapfix_circular__"
_TRUNC  = "__snapfix_truncated__"
_DEPTH  = "__snapfix_maxdepth__"


class SnapfixSerializer:
    def __init__(self, max_depth: int = 10, max_size_bytes: int = 500_000):
        self.max_depth = max_depth
        self.max_size_bytes = max_size_bytes
        self._size_counter = 0

    def serialize(self, obj: Any, _depth: int = 0, _seen: Optional[set] = None) -> Any:
        if _seen is None:
            _seen = set()
            self._size_counter = 0

        result = self._dispatch(obj, _depth, _seen)

        try:
            self._size_counter += len(json.dumps(result, default=str))
        except Exception:
            self._size_counter += 1024
        if self._size_counter > self.max_size_bytes:
            return {_TRUNC: True, "__snapfix_size__": self._size_counter}

        return result

    def _dispatch(self, obj: Any, depth: int, seen: set) -> Any:
        # depth guard (also in serialize() but _dispatch calls itself directly)
        if depth > self.max_depth:
            return {_DEPTH: True, "__snapfix_repr__": repr(obj)[:200]}
        # circular reference guard — must be per-_dispatch call, not just in serialize()
        if isinstance(obj, (dict, list, tuple, set, frozenset)):
            try:
                obj_id = id(obj)
                if obj_id in seen:
                    return {_CIRC: True}
                seen.add(obj_id)
            except Exception:
                pass
        # Singletons / primitives
        if obj is None or isinstance(obj, bool):
            return obj
        if isinstance(obj, int):
            return obj
        if isinstance(obj, str):
            return obj
        if isinstance(obj, float):
            if math.isnan(obj):
                return {_MARKER: "float", "value": "nan"}
            if math.isinf(obj):
                return {_MARKER: "float", "value": "inf" if obj > 0 else "-inf"}
            return obj
        if isinstance(obj, datetime.datetime):
            return {_MARKER: "datetime", "value": obj.isoformat()}
        if isinstance(obj, datetime.date):
            return {_MARKER: "date", "value": obj.isoformat()}
        if isinstance(obj, datetime.time):
            return {_MARKER: "time", "value": obj.isoformat()}
        if isinstance(obj, datetime.timedelta):
            return {_MARKER: "timedelta", "value": obj.total_seconds()}
        if isinstance(obj, uuid.UUID):
            return {_MARKER: "uuid", "value": str(obj)}
        if isinstance(obj, decimal.Decimal):
            return {_MARKER: "decimal", "value": str(obj)}
        if isinstance(obj, bytes):
            return {_MARKER: "bytes", "value": base64.b64encode(obj).decode()}
        if isinstance(obj, bytearray):
            return {_MARKER: "bytearray", "value": base64.b64encode(bytes(obj)).decode()}
        if isinstance(obj, pathlib.PurePath):
            return {_MARKER: "path", "value": str(obj)}
        if isinstance(obj, enum.Enum):
            return {_MARKER: "enum", "cls": type(obj).__name__,
                    "value": self._dispatch(obj.value, depth + 1, seen)}
        if isinstance(obj, (set, frozenset)):
            tag = "frozenset" if isinstance(obj, frozenset) else "set"
            try:
                items = sorted([self._dispatch(x, depth + 1, seen) for x in obj], key=str)
            except TypeError:
                items = [self._dispatch(x, depth + 1, seen) for x in obj]
            return {_MARKER: tag, "value": items}
        if isinstance(obj, tuple):
            return {_MARKER: "tuple",
                    "value": [self._dispatch(x, depth + 1, seen) for x in obj]}
        if isinstance(obj, list):
            return [self._dispatch(x, depth + 1, seen) for x in obj]
        if isinstance(obj, dict):
            return {str(k): self._dispatch(v, depth + 1, seen) for k, v in obj.items()}
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            try:
                return self._dispatch(dataclasses.asdict(obj), depth, seen)
            except Exception:
                pass
        # pydantic v2
        try:
            return self._dispatch(obj.model_dump(), depth, seen)
        except AttributeError:
            pass
        # pydantic v1
        try:
            return self._dispatch(obj.dict(), depth, seen)
        except AttributeError:
            pass
        # __dict__ fallback
        try:
            return self._dispatch(vars(obj), depth, seen)
        except TypeError:
            pass
        return {_UNSZ: True, "__snapfix_repr__": repr(obj)[:200],
                "__snapfix_type_name__": type(obj).__name__}

    def deserialize(self, data: Any) -> Any:
        if data is None or isinstance(data, (bool, int, float, str)):
            return data
        if isinstance(data, list):
            return [self.deserialize(x) for x in data]
        if isinstance(data, dict):
            marker = data.get(_MARKER)
            if marker == "datetime":
                return datetime.datetime.fromisoformat(data["value"])
            if marker == "date":
                return datetime.date.fromisoformat(data["value"])
            if marker == "time":
                return datetime.time.fromisoformat(data["value"])
            if marker == "timedelta":
                return datetime.timedelta(seconds=float(data["value"]))
            if marker == "uuid":
                return uuid.UUID(data["value"])
            if marker == "decimal":
                return decimal.Decimal(data["value"])
            if marker == "bytes":
                return base64.b64decode(data["value"].encode())
            if marker == "bytearray":
                return bytearray(base64.b64decode(data["value"].encode()))
            if marker == "path":
                return pathlib.Path(data["value"])
            if marker == "enum":
                return self.deserialize(data["value"])
            if marker in ("set", "frozenset"):
                items = [self.deserialize(x) for x in data["value"]]
                return frozenset(items) if marker == "frozenset" else set(items)
            if marker == "tuple":
                # Tuples become lists on roundtrip — documented behavior matching JSON's type system
                return [self.deserialize(x) for x in data["value"]]
            if marker == "float":
                v = data["value"]
                return float("nan") if v == "nan" else float(v)
            if any(k in data for k in (_UNSZ, _CIRC, _TRUNC, _DEPTH)):
                return data
            return {k: self.deserialize(v) for k, v in data.items()}
        return data
