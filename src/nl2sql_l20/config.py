from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    parent = config.pop("extends", None)
    if not parent:
        return config

    parent_path = Path(parent)
    if not parent_path.is_absolute():
        parent_path = path.parent / parent_path
        if not parent_path.exists():
            parent_path = path.parent.parent / parent

    return deep_merge(load_config(parent_path), config)


def require(config: dict[str, Any], dotted_key: str) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(f"Missing required config key: {dotted_key}")
        current = current[part]
    return current
