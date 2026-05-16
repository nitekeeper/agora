# tests/test_check.py
"""Tests for scripts.check (agora:check)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import check, git_helpers, paths

SAMPLE_REGISTRY = {
    "$schema": "https://nitekeeper.github.io/agora/plugins.schema.json",
    "marketplace": {
        "name": "agora",
        "owner": {"name": "nitekeeper"},
    },
    "plugins": [
        {
            "name": "atelier",
            "repository_url": "https://github.com/nitekeeper/atelier.git",
            "current_version": "v1.0.0",
            "current_sha": "a" * 40,
            "description": "Shared workspace methodology",
            "license": "MIT",
            "category": "development",
        },
        {
            "name": "memex",
            "repository_url": "https://github.com/nitekeeper/memex.git",
            "current_version": "v0.3.1",
            "current_sha": "b" * 40,
            "description": "Memory layer",
            "license": "Apache-2.0",
            "category": "productivity",
        },
    ],
}

EMPTY_REGISTRY = {
    "marketplace": {"name": "agora", "owner": {"name": "nitekeeper"}},
    "plugins": [],
}


@pytest.fixture
def tmp_paths(tmp_path: Path, monkeypatch):
    """Redirect paths.PLUGINS_JSON, CACHE_DIR, CHECK_CACHE_JSON into tmp_path."""
    plugins_json = tmp_path / "plugins.json"
    cache_dir = tmp_path / "cache"
    cache_json = cache_dir / "check-cache.json"

    monkeypatch.setattr(paths, "PLUGINS_JSON", plugins_json)
    monkeypatch.setattr(paths, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(paths, "CHECK_CACHE_JSON", cache_json)
    return plugins_json, cache_dir, cache_json


def _write_registry(plugins_json: Path, data: dict) -> None:
    plugins_json.write_text(json.dumps(data), encoding="utf-8")


def _set_ls_remote(monkeypatch, mapping: dict[str, dict[str, str] | Exception]):
    """Make git_helpers.ls_remote_tags return mapping[url] or raise it."""

    def fake(url, timeout=30):
        value = mapping.get(url)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise git_helpers.GitError(f"no mock for {url}")
        return value

    monkeypatch.setattr(check.git_helpers, "ls_remote_tags", fake)


# --------------------------------------------------------------------------- 1
def test_happy_path_two_plugins(tmp_paths, monkeypatch, capsys):
    plugins_json, _, cache_json = tmp_paths
    _write_registry(plugins_json, SAMPLE_REGISTRY)
    _set_ls_remote(
        monkeypatch,
        {
            "https://github.com/nitekeeper/atelier.git": {
                "v1.0.0": "a" * 40,
                "v1.2.0": "c" * 40,
                "v1.3.0": "d" * 40,
            },
            "https://github.com/nitekeeper/memex.git": {
                "v0.3.1": "b" * 40,
                "v0.3.0": "e" * 40,
            },
        },
    )

    rc = check.main([])
    assert rc == 0

    data = json.loads(cache_json.read_text(encoding="utf-8"))
    assert "fetched_at" in data
    assert data["include_prerelease"] is False
    assert set(data["plugins"].keys()) == {"atelier", "memex"}

    atelier = data["plugins"]["atelier"]
    assert atelier["latest_version"] == "v1.3.0"
    assert "checked_at" in atelier
    assert "error" not in atelier

    memex = data["plugins"]["memex"]
    assert memex["latest_version"] == "v0.3.1"
    assert "checked_at" in memex

    out = capsys.readouterr().out
    assert "atelier: v1.3.0" in out
    assert "memex: v0.3.1" in out
    # atelier is outdated, memex is up-to-date; no errors.
    assert "Checked 2 plugin(s) — 1 outdated, 0 errors." in out


# --------------------------------------------------------------------------- 2
def test_empty_plugins_json(tmp_paths, monkeypatch, capsys):
    plugins_json, _, cache_json = tmp_paths
    _write_registry(plugins_json, EMPTY_REGISTRY)

    rc = check.main([])
    assert rc == 0

    data = json.loads(cache_json.read_text(encoding="utf-8"))
    assert data["plugins"] == {}
    assert "fetched_at" in data
    assert data["include_prerelease"] is False


# --------------------------------------------------------------------------- 3
def test_one_plugin_errors(tmp_paths, monkeypatch, capsys):
    plugins_json, _, cache_json = tmp_paths
    _write_registry(plugins_json, SAMPLE_REGISTRY)
    _set_ls_remote(
        monkeypatch,
        {
            "https://github.com/nitekeeper/atelier.git": {"v1.0.0": "a" * 40},
            "https://github.com/nitekeeper/memex.git": git_helpers.GitError(
                "git ls-remote failed for memex: network down"
            ),
        },
    )

    rc = check.main([])
    assert rc == 0

    data = json.loads(cache_json.read_text(encoding="utf-8"))
    atelier = data["plugins"]["atelier"]
    assert atelier["latest_version"] == "v1.0.0"
    assert "error" not in atelier

    memex = data["plugins"]["memex"]
    assert memex["latest_version"] is None
    assert "git ls-remote failed" in memex["error"]
    assert "checked_at" in memex

    out = capsys.readouterr().out
    assert "memex: ERROR" in out
    assert "Checked 2 plugin(s) — 0 outdated, 1 errors." in out


# --------------------------------------------------------------------------- 4
def test_ttl_fresh_no_force(tmp_paths, monkeypatch, capsys):
    plugins_json, cache_dir, cache_json = tmp_paths
    _write_registry(plugins_json, SAMPLE_REGISTRY)

    # Pre-populate a fresh cache (1h old).
    cache_dir.mkdir(parents=True, exist_ok=True)
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    cache_json.write_text(
        json.dumps(
            {
                "fetched_at": recent,
                "include_prerelease": False,
                "plugins": {},
            }
        ),
        encoding="utf-8",
    )

    # Sentinel — fail if git is called.
    called = {"n": 0}

    def boom(url, timeout=30):
        called["n"] += 1
        raise AssertionError("ls_remote_tags should not be called when cache is fresh")

    monkeypatch.setattr(check.git_helpers, "ls_remote_tags", boom)

    rc = check.main([])
    assert rc == 0
    assert called["n"] == 0

    out = capsys.readouterr().out
    assert "cache is fresh" in out
    assert "--force" in out


# --------------------------------------------------------------------------- 5
def test_ttl_stale_refreshes(tmp_paths, monkeypatch, capsys):
    plugins_json, cache_dir, cache_json = tmp_paths
    _write_registry(plugins_json, SAMPLE_REGISTRY)

    cache_dir.mkdir(parents=True, exist_ok=True)
    stale = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    cache_json.write_text(
        json.dumps(
            {
                "fetched_at": stale,
                "include_prerelease": False,
                "plugins": {},
            }
        ),
        encoding="utf-8",
    )

    _set_ls_remote(
        monkeypatch,
        {
            "https://github.com/nitekeeper/atelier.git": {"v2.0.0": "f" * 40},
            "https://github.com/nitekeeper/memex.git": {"v0.4.0": "g" * 40},
        },
    )

    rc = check.main([])
    assert rc == 0

    data = json.loads(cache_json.read_text(encoding="utf-8"))
    assert data["plugins"]["atelier"]["latest_version"] == "v2.0.0"
    assert data["plugins"]["memex"]["latest_version"] == "v0.4.0"


# --------------------------------------------------------------------------- 6
def test_force_ignores_ttl(tmp_paths, monkeypatch, capsys):
    plugins_json, cache_dir, cache_json = tmp_paths
    _write_registry(plugins_json, SAMPLE_REGISTRY)

    cache_dir.mkdir(parents=True, exist_ok=True)
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    cache_json.write_text(
        json.dumps(
            {
                "fetched_at": recent,
                "include_prerelease": False,
                "plugins": {},
            }
        ),
        encoding="utf-8",
    )

    _set_ls_remote(
        monkeypatch,
        {
            "https://github.com/nitekeeper/atelier.git": {"v9.9.9": "h" * 40},
            "https://github.com/nitekeeper/memex.git": {"v0.3.1": "b" * 40},
        },
    )

    rc = check.main(["--force"])
    assert rc == 0

    data = json.loads(cache_json.read_text(encoding="utf-8"))
    assert data["plugins"]["atelier"]["latest_version"] == "v9.9.9"


# --------------------------------------------------------------------------- 7
def test_include_prerelease(tmp_paths, monkeypatch, capsys):
    plugins_json, _, cache_json = tmp_paths
    # Single-plugin registry for clarity.
    reg = {
        "marketplace": {"name": "agora", "owner": {"name": "nitekeeper"}},
        "plugins": [
            {
                "name": "atelier",
                "repository_url": "https://github.com/nitekeeper/atelier.git",
                "current_version": "v1.0.0",
                "current_sha": "a" * 40,
                "description": "x",
                "license": "MIT",
                "category": "development",
            },
        ],
    }
    _write_registry(plugins_json, reg)
    _set_ls_remote(
        monkeypatch,
        {
            "https://github.com/nitekeeper/atelier.git": {
                "v1.0.0": "a" * 40,
                "v2.0.0-rc1": "i" * 40,
            },
        },
    )

    # Without flag: picks v1.0.0 (skips prerelease).
    rc = check.main([])
    assert rc == 0
    data = json.loads(cache_json.read_text(encoding="utf-8"))
    assert data["plugins"]["atelier"]["latest_version"] == "v1.0.0"
    assert data["include_prerelease"] is False

    # With flag (use --force since cache is fresh now).
    rc = check.main(["--include-prerelease", "--force"])
    assert rc == 0
    data = json.loads(cache_json.read_text(encoding="utf-8"))
    assert data["plugins"]["atelier"]["latest_version"] == "v2.0.0-rc1"
    assert data["include_prerelease"] is True


# --------------------------------------------------------------------------- 8
def test_json_mode(tmp_paths, monkeypatch, capsys):
    plugins_json, _, cache_json = tmp_paths
    _write_registry(plugins_json, SAMPLE_REGISTRY)
    _set_ls_remote(
        monkeypatch,
        {
            "https://github.com/nitekeeper/atelier.git": {"v1.3.0": "d" * 40},
            "https://github.com/nitekeeper/memex.git": {"v0.3.1": "b" * 40},
        },
    )

    rc = check.main(["--json"])
    assert rc == 0

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "fetched_at" in parsed
    assert parsed["include_prerelease"] is False
    assert parsed["plugins"]["atelier"]["latest_version"] == "v1.3.0"

    # Cache file still written.
    on_disk = json.loads(cache_json.read_text(encoding="utf-8"))
    assert on_disk["plugins"]["atelier"]["latest_version"] == "v1.3.0"


# --------------------------------------------------------------------------- 9
def test_no_tags_plugin(tmp_paths, monkeypatch, capsys):
    plugins_json, _, cache_json = tmp_paths
    reg = {
        "marketplace": {"name": "agora", "owner": {"name": "nitekeeper"}},
        "plugins": [
            {
                "name": "empty",
                "repository_url": "https://github.com/nitekeeper/empty.git",
                "current_version": "v0.0.0",
                "current_sha": "0" * 40,
                "description": "x",
                "license": "MIT",
                "category": "development",
            },
        ],
    }
    _write_registry(plugins_json, reg)
    _set_ls_remote(
        monkeypatch,
        {
            "https://github.com/nitekeeper/empty.git": {},
        },
    )

    rc = check.main([])
    assert rc == 0

    data = json.loads(cache_json.read_text(encoding="utf-8"))
    entry = data["plugins"]["empty"]
    assert entry["latest_version"] is None
    assert "error" not in entry
    assert "checked_at" in entry


# --------------------------------------------------------------------------- 10
def test_cache_dir_autocreated(tmp_paths, monkeypatch, capsys):
    plugins_json, cache_dir, cache_json = tmp_paths
    _write_registry(plugins_json, EMPTY_REGISTRY)
    # Ensure cache_dir really doesn't exist.
    assert not cache_dir.exists()

    rc = check.main([])
    assert rc == 0

    assert cache_dir.is_dir()
    assert cache_json.exists()


# --------------------------------------------------------------------------- 11
def test_fetched_at_z_suffix(tmp_paths, monkeypatch, capsys):
    plugins_json, _, cache_json = tmp_paths
    _write_registry(plugins_json, EMPTY_REGISTRY)

    rc = check.main([])
    assert rc == 0

    data = json.loads(cache_json.read_text(encoding="utf-8"))
    assert isinstance(data["fetched_at"], str)
    assert data["fetched_at"].endswith("Z")
    assert "+00:00" not in data["fetched_at"]
