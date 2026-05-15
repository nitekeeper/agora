# tests/test_compile.py
"""Tests for scripts.compile."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts import paths
from scripts.compile import (
    MARKETPLACE_SCHEMA_URL,
    CompileError,
    compile_marketplace,
    compile_to_disk,
)


def _base_marketplace() -> dict:
    return {
        "name": "agora",
        "description": "Custom Claude Code plugin marketplace",
        "owner": {"name": "nitekeeper"},
    }


def _full_plugin() -> dict:
    return {
        "name": "nitekeeper-atelier",
        "repository_url": "https://github.com/nitekeeper/atelier.git",
        "current_version": "v1.0.0",
        "current_sha": "abc1230000000000000000000000000000000000",
        "description": "Shared workspace methodology",
        "license": "MIT",
        "category": "development",
        "keywords": ["workspace", "methodology"],
        "author": {"name": "nitekeeper"},
        "homepage": "https://example.com/atelier",
        "registered_at": "2026-05-15T00:00:00Z",
        "updated_at": "2026-05-15T00:00:00Z",
    }


def _minimal_plugin(name: str = "owner-min") -> dict:
    return {
        "name": name,
        "repository_url": f"https://github.com/owner/{name}.git",
        "current_version": "v0.1.0",
        "current_sha": "0" * 40,
        "description": "Minimal plugin",
        "license": "MIT",
    }


def test_compile_empty_plugins_array() -> None:
    data = {"marketplace": _base_marketplace(), "plugins": []}
    out = compile_marketplace(data)
    assert out["$schema"] == MARKETPLACE_SCHEMA_URL
    assert out["name"] == "agora"
    assert out["description"] == "Custom Claude Code plugin marketplace"
    assert out["owner"] == {"name": "nitekeeper"}
    assert out["plugins"] == []


def test_compile_full_plugin_maps_source_and_passthroughs() -> None:
    data = {"marketplace": _base_marketplace(), "plugins": [_full_plugin()]}
    out = compile_marketplace(data)
    assert len(out["plugins"]) == 1
    p = out["plugins"][0]
    assert p["name"] == "nitekeeper-atelier"
    assert p["description"] == "Shared workspace methodology"
    assert p["source"] == {
        "source": "url",
        "url": "https://github.com/nitekeeper/atelier.git",
        "ref": "v1.0.0",
        "sha": "abc1230000000000000000000000000000000000",
    }
    assert p["category"] == "development"
    assert p["keywords"] == ["workspace", "methodology"]
    assert p["author"] == {"name": "nitekeeper"}
    assert p["homepage"] == "https://example.com/atelier"


def test_compile_minimal_plugin_omits_absent_optionals() -> None:
    data = {"marketplace": _base_marketplace(), "plugins": [_minimal_plugin()]}
    out = compile_marketplace(data)
    p = out["plugins"][0]
    for absent in ("category", "keywords", "author", "homepage"):
        assert absent not in p, f"{absent} should be absent, got: {p}"


def test_compile_drops_license_and_timestamps() -> None:
    data = {"marketplace": _base_marketplace(), "plugins": [_full_plugin()]}
    out = compile_marketplace(data)
    p = out["plugins"][0]
    for dropped in ("license", "registered_at", "updated_at", "repository_url",
                    "current_version", "current_sha"):
        assert dropped not in p, f"{dropped} should not appear in output"


def test_compile_preserves_plugin_order() -> None:
    names = ["owner-a", "owner-b", "owner-c", "owner-d"]
    plugins = [_minimal_plugin(n) for n in names]
    data = {"marketplace": _base_marketplace(), "plugins": plugins}
    out = compile_marketplace(data)
    assert [p["name"] for p in out["plugins"]] == names


def test_compile_raises_on_missing_marketplace_name() -> None:
    bad = _base_marketplace()
    del bad["name"]
    data = {"marketplace": bad, "plugins": []}
    with pytest.raises(CompileError, match="name"):
        compile_marketplace(data)


def test_compile_raises_on_plugin_missing_current_sha() -> None:
    plugin = _minimal_plugin()
    del plugin["current_sha"]
    data = {"marketplace": _base_marketplace(), "plugins": [plugin]}
    with pytest.raises(CompileError, match="current_sha"):
        compile_marketplace(data)


def test_compile_raises_when_plugins_is_not_a_list() -> None:
    data = {"marketplace": _base_marketplace(), "plugins": {"not": "a list"}}
    with pytest.raises(CompileError, match="must be a list"):
        compile_marketplace(data)


def test_compile_to_disk_reads_and_writes(tmp_path: Path) -> None:
    plugins_path = tmp_path / "plugins.json"
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"
    src = {"marketplace": _base_marketplace(), "plugins": [_full_plugin()]}
    plugins_path.write_text(json.dumps(src, indent=2) + "\n", encoding="utf-8")

    result = compile_to_disk(plugins_path, marketplace_path)
    assert marketplace_path.exists()
    on_disk = json.loads(marketplace_path.read_text(encoding="utf-8"))
    assert on_disk == result
    assert on_disk == compile_marketplace(src)
    # Trailing newline + 2-space indent style.
    raw = marketplace_path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert '\n  "name":' in raw


def test_compile_to_disk_raises_when_plugins_json_missing(tmp_path: Path) -> None:
    plugins_path = tmp_path / "plugins.json"
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"
    with pytest.raises(CompileError, match="not found"):
        compile_to_disk(plugins_path, marketplace_path)


def test_compile_to_disk_raises_on_malformed_json(tmp_path: Path) -> None:
    plugins_path = tmp_path / "plugins.json"
    plugins_path.write_text("{not valid json", encoding="utf-8")
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"
    with pytest.raises(CompileError, match="not valid JSON"):
        compile_to_disk(plugins_path, marketplace_path)


def test_compile_real_plugins_json_round_trip() -> None:
    raw = paths.PLUGINS_JSON.read_text(encoding="utf-8")
    data = json.loads(raw)

    schema = json.loads(paths.SCHEMA_JSON.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)

    out = compile_marketplace(data)
    assert isinstance(out, dict)
    for key in ("$schema", "name", "description", "owner", "plugins"):
        assert key in out
    assert isinstance(out["plugins"], list)
    # Output is JSON-serializable.
    json.dumps(out)
