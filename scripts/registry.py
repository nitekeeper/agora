# scripts/registry.py
"""Read/write helpers for plugins.json. save_registry() recompiles and atomically
writes both plugins.json and the derived marketplace.json in one operation.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.atomic import atomic_write_pair
from scripts.compile import compile_marketplace
from scripts.paths import MARKETPLACE_JSON, PLUGINS_JSON


def load_registry(path: Path = PLUGINS_JSON) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(
    data: dict,
    plugins_path: Path = PLUGINS_JSON,
    marketplace_path: Path = MARKETPLACE_JSON,
) -> None:
    plugins_content = json.dumps(data, indent=2) + "\n"
    marketplace_content = json.dumps(compile_marketplace(data), indent=2) + "\n"
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_pair(
        plugins_path, plugins_content,
        marketplace_path, marketplace_content,
    )


def find_plugin(data: dict, name: str) -> tuple[int, dict] | None:
    """Return (index, entry) for the plugin with the given name, or None."""
    for i, p in enumerate(data.get("plugins", [])):
        if p.get("name") == name:
            return i, p
    return None
