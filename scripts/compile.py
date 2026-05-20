# scripts/compile.py
"""Translate plugins.json (source of truth) -> .claude-plugin/marketplace.json.

The marketplace.json shape matches what Claude Code's /plugins > Marketplaces
UI expects: each plugin has a `source` object (instead of the flat
repository_url/current_version/current_sha triple) and source-only fields like
license, registered_at, updated_at are dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Support both `python3 -m scripts.compile` and `python3 scripts/compile.py`
# invocations by ensuring the repo root is on sys.path for the direct case.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.atomic import atomic_write
from scripts.paths import MARKETPLACE_JSON, PLUGINS_JSON

MARKETPLACE_SCHEMA_URL = "https://anthropic.com/claude-code/marketplace.schema.json"

# Fields copied straight through if present.
_OPTIONAL_PASSTHROUGH = ("category", "keywords", "author", "homepage")

# Required per-plugin fields in plugins.json.
_REQUIRED_PLUGIN_FIELDS = (
    "name",
    "repository_url",
    "current_version",
    "current_sha",
    "description",
)


class CompileError(Exception):
    """Raised when plugins.json is missing, malformed, or fails validation."""


def _validate_marketplace_block(data: dict) -> dict:
    block = data.get("marketplace")
    if not isinstance(block, dict):
        raise CompileError("plugins.json missing required 'marketplace' object")
    for field in ("name", "description", "owner"):
        if field not in block:
            raise CompileError(f"plugins.json marketplace block missing required field '{field}'")
    return block


def _validate_plugins(data: dict) -> list:
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        raise CompileError("plugins.json 'plugins' must be a list")
    return plugins


def _compile_plugin(plugin: dict) -> dict:
    for field in _REQUIRED_PLUGIN_FIELDS:
        if field not in plugin:
            name = plugin.get("name", "<unknown>")
            raise CompileError(f"plugin '{name}' missing required field '{field}'")

    out: dict = {
        "name": plugin["name"],
        "description": plugin["description"],
        "source": {
            "source": "url",
            "url": plugin["repository_url"],
            "ref": plugin["current_version"],
            "sha": plugin["current_sha"],
        },
    }
    for key in _OPTIONAL_PASSTHROUGH:
        if key in plugin:
            out[key] = plugin[key]
    return out


def compile_marketplace(plugins_data: dict) -> dict:
    """Pure function: plugins.json content -> marketplace.json content."""
    if not isinstance(plugins_data, dict):
        raise CompileError("plugins.json root must be an object")
    marketplace = _validate_marketplace_block(plugins_data)
    plugins = _validate_plugins(plugins_data)

    return {
        "$schema": MARKETPLACE_SCHEMA_URL,
        "name": marketplace["name"],
        "description": marketplace["description"],
        "owner": marketplace["owner"],
        "plugins": [_compile_plugin(p) for p in plugins],
    }


def compile_to_disk(
    plugins_path: Path = PLUGINS_JSON,
    marketplace_path: Path = MARKETPLACE_JSON,
) -> dict:
    """Read plugins.json, compile, atomic-write marketplace.json. Returns dict."""
    if not plugins_path.exists():
        raise CompileError("plugins.json not found")
    try:
        raw = plugins_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CompileError(f"plugins.json is not valid JSON: {e}") from e

    result = compile_marketplace(data)
    content = json.dumps(result, indent=2) + "\n"
    atomic_write(marketplace_path, content)
    return result


def main() -> int:
    try:
        result = compile_to_disk()
    except CompileError as e:
        print(f"compile failed: {e}", file=sys.stderr)
        return 1
    count = len(result.get("plugins", []))
    print(f"Compiled {count} plugins -> .claude-plugin/marketplace.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
