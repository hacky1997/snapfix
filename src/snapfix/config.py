from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

import yaml

DEFAULT_SCRUB_FIELDS: list[str] = [
    "email","password","passwd","token","secret","api_key","apikey",
    "access_token","refresh_token","ssn","credit_card","card_number",
    "cvv","phone","mobile","dob","date_of_birth","address","ip_address",
    "authorization","auth","bearer",
]

@dataclass
class SnapfixConfig:
    output_dir: pathlib.Path = pathlib.Path("tests/fixtures")
    default_scrub_fields: list[str] = field(default_factory=lambda: list(DEFAULT_SCRUB_FIELDS))
    max_depth: int = 10
    max_size_bytes: int = 500_000
    enabled: bool = True

    @classmethod
    def from_env(cls) -> SnapfixConfig:
        return cls(
            output_dir=pathlib.Path(os.environ.get("SNAPFIX_OUTPUT_DIR", "tests/fixtures")),
            max_depth=int(os.environ.get("SNAPFIX_MAX_DEPTH", 10)),
            max_size_bytes=int(os.environ.get("SNAPFIX_MAX_SIZE", 500_000)),
            enabled=os.environ.get("SNAPFIX_ENABLED", "true").lower() != "false",
        )

    @classmethod
    def from_yaml(cls, path: pathlib.Path) -> SnapfixConfig:
        if not path.exists():
            return cls.from_env()
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception:
            return cls.from_env()
        sf = data.get("snapfix", {})
        cfg = cls.from_env()
        if "output_dir" in sf:
            cfg.output_dir = pathlib.Path(sf["output_dir"])
        if "max_depth" in sf:
            cfg.max_depth = int(sf["max_depth"])
        if "max_size_bytes" in sf:
            cfg.max_size_bytes = int(sf["max_size_bytes"])
        if "enabled" in sf:
            cfg.enabled = bool(sf["enabled"])
        return cfg
