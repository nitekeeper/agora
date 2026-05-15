# tests/test_plugin_unregister.py
"""Tests for scripts.plugin_unregister (agora:plugin-unregister)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import paths, plugin_unregister


SAMPLE_PLUGINS = {
    "$schema": "https://nitekeeper.github.io/agora/plugins.schema.json",
    "marketplace": {
        "name": "agora",
        "description": "Custom Claude Code plugin marketplace",
        "owner": {"name": "nitekeeper"},
    },
    "plugins": [
        {
            "name": "atelier",
            "repository_url": "https://github.com/nitekeeper/atelier.git",
            "current_version": "v1.0.0",
            "current_sha": "abc1230000000000000000000000000000000000",
            "description": "Shared workspace methodology",
            "license": "MIT",
            "category": "development",
        },
        {
            "name": "memex",
            "repository_url": "https://github.com/nitekeeper/memex.git",
            "current_version": "v0.3.1",
            "current_sha": "def4560000000000000000000000000000000000",
            "description": "Memory layer",
            "license": "Apache-2.0",
            "category": "productivity",
        },
    ],
}


def _setup_registry(tmp_path: Path, monkeypatch, data: dict) -> tuple[Path, Path]:
    plugins_path = tmp_path / "plugins.json"
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    plugins_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    # Seed marketplace.json so we can assert it gets regenerated.
    marketplace_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(paths, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(paths, "MARKETPLACE_JSON", marketplace_path)
    # registry.py imported these by name and uses them as default args (bound
    # at function-definition time), so patch the module attributes AND wrap
    # the functions to redirect to the tmp paths.
    from scripts import registry as _registry
    monkeypatch.setattr(_registry, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(_registry, "MARKETPLACE_JSON", marketplace_path)

    real_load = _registry.load_registry
    real_save = _registry.save_registry
    monkeypatch.setattr(
        _registry,
        "load_registry",
        lambda path=plugins_path: real_load(path),
    )
    monkeypatch.setattr(
        _registry,
        "save_registry",
        lambda data, p=plugins_path, m=marketplace_path: real_save(data, p, m),
    )
    return plugins_path, marketplace_path


# --------------------------------------------------------------------------- 1
def test_happy_path_with_yes(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path, marketplace_path = _setup_registry(
        tmp_path, monkeypatch, SAMPLE_PLUGINS
    )

    rc = plugin_unregister.main(["atelier", "--yes"])
    captured = capsys.readouterr()

    assert rc == 0
    data = json.loads(plugins_path.read_text(encoding="utf-8"))
    names = [p["name"] for p in data["plugins"]]
    assert names == ["memex"]

    market = json.loads(marketplace_path.read_text(encoding="utf-8"))
    market_names = [p["name"] for p in market["plugins"]]
    assert market_names == ["memex"]
    assert "Removed plugin 'atelier'." in captured.out


# --------------------------------------------------------------------------- 2
def test_plugin_not_found(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path, _ = _setup_registry(tmp_path, monkeypatch, SAMPLE_PLUGINS)

    rc = plugin_unregister.main(["does-not-exist", "--yes"])
    captured = capsys.readouterr()

    assert rc == 1
    assert "plugin not found: does-not-exist" in captured.err
    # plugins.json unchanged
    data = json.loads(plugins_path.read_text(encoding="utf-8"))
    assert len(data["plugins"]) == 2


# --------------------------------------------------------------------------- 3
def test_confirmation_accepted(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path, _ = _setup_registry(tmp_path, monkeypatch, SAMPLE_PLUGINS)
    monkeypatch.setattr("builtins.input", lambda *_args, **_kw: "y")

    rc = plugin_unregister.main(["atelier"])
    captured = capsys.readouterr()

    assert rc == 0
    data = json.loads(plugins_path.read_text(encoding="utf-8"))
    assert [p["name"] for p in data["plugins"]] == ["memex"]
    assert "Removed plugin 'atelier'." in captured.out


# --------------------------------------------------------------------------- 4
def test_confirmation_declined(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path, _ = _setup_registry(tmp_path, monkeypatch, SAMPLE_PLUGINS)
    monkeypatch.setattr("builtins.input", lambda *_args, **_kw: "")

    rc = plugin_unregister.main(["atelier"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "cancelled" in captured.out
    # plugins.json unchanged
    data = json.loads(plugins_path.read_text(encoding="utf-8"))
    assert [p["name"] for p in data["plugins"]] == [
        "atelier",
        "memex",
    ]


# --------------------------------------------------------------------------- 5
def test_multiple_plugins_only_target_removed(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    data = json.loads(json.dumps(SAMPLE_PLUGINS))
    data["plugins"].append({
        "name": "agora",
        "repository_url": "https://github.com/nitekeeper/agora.git",
        "current_version": "v0.1.0",
        "current_sha": "0123450000000000000000000000000000000000",
        "description": "Marketplace tooling",
        "license": "MIT",
        "category": "development",
    })
    plugins_path, _ = _setup_registry(tmp_path, monkeypatch, data)

    rc = plugin_unregister.main(["memex", "--yes"])
    assert rc == 0

    updated = json.loads(plugins_path.read_text(encoding="utf-8"))
    names = [p["name"] for p in updated["plugins"]]
    # Order preserved, only memex removed.
    assert names == ["atelier", "agora"]
    # Other entries untouched (deep equality on the surviving fields).
    atelier = next(p for p in updated["plugins"] if p["name"] == "atelier")
    assert atelier["current_sha"] == "abc1230000000000000000000000000000000000"
    assert atelier["license"] == "MIT"


# --------------------------------------------------------------------------- 6
def test_marketplace_reflects_removal(tmp_path: Path, monkeypatch) -> None:
    _, marketplace_path = _setup_registry(tmp_path, monkeypatch, SAMPLE_PLUGINS)

    rc = plugin_unregister.main(["memex", "--yes"])
    assert rc == 0

    market = json.loads(marketplace_path.read_text(encoding="utf-8"))
    market_names = [p["name"] for p in market["plugins"]]
    assert "memex" not in market_names
    assert market_names == ["atelier"]
    # Marketplace shape: source object present, license stripped.
    entry = market["plugins"][0]
    assert "source" in entry
    assert entry["source"]["url"] == "https://github.com/nitekeeper/atelier.git"
    assert "license" not in entry
