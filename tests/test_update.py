# tests/test_update.py
"""Tests for scripts.update (agora:update)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import git_helpers, registry, update
from scripts.git_helpers import GitError


SHA_ATELIER_OLD = "a" * 40
SHA_ATELIER_NEW = "b" * 40
SHA_MEMEX = "c" * 40
SHA_FOO_PRERELEASE = "d" * 40


def _base_data() -> dict:
    return {
        "$schema": "https://nitekeeper.github.io/agora/plugins.schema.json",
        "marketplace": {
            "name": "agora",
            "description": "Custom Claude Code plugin marketplace",
            "owner": {"name": "nitekeeper"},
        },
        "plugins": [
            {
                "name": "nitekeeper-atelier",
                "repository_url": "https://github.com/nitekeeper/atelier.git",
                "current_version": "v1.0.0",
                "current_sha": SHA_ATELIER_OLD,
                "description": "Shared workspace methodology",
                "registered_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-05-01T00:00:00Z",
            },
            {
                "name": "nitekeeper-memex",
                "repository_url": "https://github.com/nitekeeper/memex.git",
                "current_version": "v0.3.1",
                "current_sha": SHA_MEMEX,
                "description": "Memory layer",
                "registered_at": "2026-05-02T00:00:00Z",
                "updated_at": "2026-05-02T00:00:00Z",
            },
        ],
    }


@pytest.fixture
def patched_paths(tmp_path, monkeypatch):
    """Redirect plugins.json + marketplace.json into tmp_path and seed them."""
    plugins_path = tmp_path / "plugins.json"
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)

    data = _base_data()
    plugins_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Monkeypatch the names registry actually uses (imported at module load).
    monkeypatch.setattr(registry, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(registry, "MARKETPLACE_JSON", marketplace_path)
    # Some code paths import via scripts.paths; keep those in sync just in case.
    from scripts import paths as paths_mod
    monkeypatch.setattr(paths_mod, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(paths_mod, "MARKETPLACE_JSON", marketplace_path)

    # load_registry / save_registry have default args captured at function-def
    # time; bind them to the tmp paths so the script picks them up without
    # plumbing in --plugins arguments.
    real_load = registry.load_registry
    real_save = registry.save_registry

    def load_redirected(path=plugins_path):
        return real_load(path)

    def save_redirected(data, plugins_path_=plugins_path, marketplace_path_=marketplace_path):
        return real_save(data, plugins_path_, marketplace_path_)

    monkeypatch.setattr(registry, "load_registry", load_redirected)
    monkeypatch.setattr(registry, "save_registry", save_redirected)
    # update.py imports `registry` as a module alias, so the patched attributes
    # are visible to it automatically (same module object).

    return plugins_path, marketplace_path


def _patch_tags(monkeypatch, mapping: dict):
    """Make git_helpers.ls_remote_tags return per-URL responses.

    mapping: {url -> dict_or_exception}. If the value is an Exception
    instance, it is raised.
    """
    def fake(url, timeout=30):
        if url not in mapping:
            raise GitError(f"unexpected url: {url}")
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return dict(value)

    monkeypatch.setattr(git_helpers, "ls_remote_tags", fake)
    # update.py also imports the symbol; patch the module attribute too.
    monkeypatch.setattr(update.git_helpers, "ls_remote_tags", fake)


# --------------------------------------------------------------------------- 1
def test_single_plugin_newer_tag_updates(patched_paths, monkeypatch, capsys):
    plugins_path, marketplace_path = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
            "v1.3.0": SHA_ATELIER_NEW,
        },
    })

    rc = update.main(["nitekeeper-atelier"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "nitekeeper-atelier: v1.0.0 -> v1.3.0" in out
    assert "Updated 1 plugin(s)." in out

    plugins = json.loads(plugins_path.read_text(encoding="utf-8"))
    atelier = next(p for p in plugins["plugins"] if p["name"] == "nitekeeper-atelier")
    assert atelier["current_version"] == "v1.3.0"
    assert atelier["current_sha"] == SHA_ATELIER_NEW

    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    mp_atelier = next(p for p in marketplace["plugins"] if p["name"] == "nitekeeper-atelier")
    assert mp_atelier["source"]["ref"] == "v1.3.0"
    assert mp_atelier["source"]["sha"] == SHA_ATELIER_NEW


# --------------------------------------------------------------------------- 2
def test_single_plugin_up_to_date(patched_paths, monkeypatch, capsys):
    plugins_path, _ = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
        },
    })

    before = plugins_path.read_text(encoding="utf-8")
    rc = update.main(["nitekeeper-atelier"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "up to date" in out
    assert "v1.0.0" in out
    assert "No updates available." in out

    after = plugins_path.read_text(encoding="utf-8")
    assert before == after


# --------------------------------------------------------------------------- 3
def test_all_mixed_states(patched_paths, monkeypatch, capsys):
    plugins_path, _ = patched_paths
    # Add a third plugin that will hit a network error.
    data = json.loads(plugins_path.read_text(encoding="utf-8"))
    data["plugins"].append({
        "name": "nitekeeper-foo",
        "repository_url": "https://github.com/nitekeeper/foo.git",
        "current_version": "v0.1.0",
        "current_sha": "e" * 40,
        "description": "foo",
        "registered_at": "2026-05-03T00:00:00Z",
        "updated_at": "2026-05-03T00:00:00Z",
    })
    plugins_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
            "v1.3.0": SHA_ATELIER_NEW,
        },
        "https://github.com/nitekeeper/memex.git": {
            "v0.3.1": SHA_MEMEX,
        },
        "https://github.com/nitekeeper/foo.git": GitError("network down"),
    })

    rc = update.main(["--all"])
    assert rc == 0

    cap = capsys.readouterr()
    assert "nitekeeper-atelier: v1.0.0 -> v1.3.0" in cap.out
    assert "nitekeeper-memex: up to date (v0.3.1)" in cap.out
    assert "nitekeeper-foo: error" in cap.out
    assert "nitekeeper-foo: network down" in cap.err
    assert "Updated 1 plugin(s)." in cap.out

    plugins = json.loads(plugins_path.read_text(encoding="utf-8"))
    atelier = next(p for p in plugins["plugins"] if p["name"] == "nitekeeper-atelier")
    memex = next(p for p in plugins["plugins"] if p["name"] == "nitekeeper-memex")
    foo = next(p for p in plugins["plugins"] if p["name"] == "nitekeeper-foo")
    assert atelier["current_version"] == "v1.3.0"
    assert memex["current_version"] == "v0.3.1"
    assert foo["current_version"] == "v0.1.0"


# --------------------------------------------------------------------------- 4
def test_all_up_to_date(patched_paths, monkeypatch, capsys):
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {"v1.0.0": SHA_ATELIER_OLD},
        "https://github.com/nitekeeper/memex.git": {"v0.3.1": SHA_MEMEX},
    })

    rc = update.main(["--all"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No updates available." in out


# --------------------------------------------------------------------------- 5
def test_dry_run_no_write(patched_paths, monkeypatch, capsys):
    plugins_path, marketplace_path = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
            "v1.3.0": SHA_ATELIER_NEW,
        },
    })
    before = plugins_path.read_text(encoding="utf-8")

    rc = update.main(["nitekeeper-atelier", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "would be updated" in out
    assert "nitekeeper-atelier: v1.0.0 -> v1.3.0" in out

    # plugins.json untouched, marketplace.json not written.
    assert plugins_path.read_text(encoding="utf-8") == before
    assert not marketplace_path.exists()


# --------------------------------------------------------------------------- 6
def test_include_prerelease(patched_paths, monkeypatch, capsys):
    plugins_path, _ = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
            "v1.1.0-rc.1": SHA_FOO_PRERELEASE,
        },
    })

    # Without flag: stable v1.0.0 is the latest, no update.
    rc = update.main(["nitekeeper-atelier"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "up to date" in out

    # With flag: prerelease wins, update happens.
    rc = update.main(["nitekeeper-atelier", "--include-prerelease"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "v1.0.0 -> v1.1.0-rc.1" in out

    plugins = json.loads(plugins_path.read_text(encoding="utf-8"))
    atelier = next(p for p in plugins["plugins"] if p["name"] == "nitekeeper-atelier")
    assert atelier["current_version"] == "v1.1.0-rc.1"
    assert atelier["current_sha"] == SHA_FOO_PRERELEASE


# --------------------------------------------------------------------------- 7
def test_plugin_not_found_exits_1(patched_paths, monkeypatch, capsys):
    rc = update.main(["does-not-exist"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "plugin not found: does-not-exist" in err


# --------------------------------------------------------------------------- 8
def test_no_args_exits_1(patched_paths, capsys):
    rc = update.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "usage" in err.lower()


# --------------------------------------------------------------------------- 9
def test_all_batch_continues_on_network_failure(patched_paths, monkeypatch, capsys):
    plugins_path, _ = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": GitError("ls-remote failed"),
        "https://github.com/nitekeeper/memex.git": {
            "v0.3.1": SHA_MEMEX,
            "v0.4.0": "f" * 40,
        },
    })

    rc = update.main(["--all"])
    assert rc == 0
    cap = capsys.readouterr()
    assert "nitekeeper-atelier: ls-remote failed" in cap.err
    assert "nitekeeper-atelier: error" in cap.out
    assert "nitekeeper-memex: v0.3.1 -> v0.4.0" in cap.out

    plugins = json.loads(plugins_path.read_text(encoding="utf-8"))
    memex = next(p for p in plugins["plugins"] if p["name"] == "nitekeeper-memex")
    assert memex["current_version"] == "v0.4.0"


# --------------------------------------------------------------------------- 10
def test_updated_at_bumped_only_on_change(patched_paths, monkeypatch, capsys):
    plugins_path, _ = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
            "v1.3.0": SHA_ATELIER_NEW,
        },
        "https://github.com/nitekeeper/memex.git": {
            "v0.3.1": SHA_MEMEX,
        },
    })

    before = json.loads(plugins_path.read_text(encoding="utf-8"))
    atelier_before = next(p for p in before["plugins"] if p["name"] == "nitekeeper-atelier")
    memex_before = next(p for p in before["plugins"] if p["name"] == "nitekeeper-memex")
    atelier_updated_before = atelier_before["updated_at"]
    memex_updated_before = memex_before["updated_at"]

    rc = update.main(["--all"])
    assert rc == 0

    after = json.loads(plugins_path.read_text(encoding="utf-8"))
    atelier_after = next(p for p in after["plugins"] if p["name"] == "nitekeeper-atelier")
    memex_after = next(p for p in after["plugins"] if p["name"] == "nitekeeper-memex")

    assert atelier_after["updated_at"] != atelier_updated_before
    assert memex_after["updated_at"] == memex_updated_before


# --------------------------------------------------------------------------- 11
def test_registered_at_preserved(patched_paths, monkeypatch, capsys):
    plugins_path, _ = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
            "v1.3.0": SHA_ATELIER_NEW,
        },
    })

    before = json.loads(plugins_path.read_text(encoding="utf-8"))
    registered_before = next(
        p for p in before["plugins"] if p["name"] == "nitekeeper-atelier"
    )["registered_at"]

    rc = update.main(["nitekeeper-atelier"])
    assert rc == 0

    after = json.loads(plugins_path.read_text(encoding="utf-8"))
    registered_after = next(
        p for p in after["plugins"] if p["name"] == "nitekeeper-atelier"
    )["registered_at"]
    assert registered_after == registered_before


# --------------------------------------------------------------------------- 12
def test_marketplace_reflects_new_ref_and_sha(patched_paths, monkeypatch, capsys):
    plugins_path, marketplace_path = patched_paths
    _patch_tags(monkeypatch, {
        "https://github.com/nitekeeper/atelier.git": {
            "v1.0.0": SHA_ATELIER_OLD,
            "v2.0.0": SHA_ATELIER_NEW,
        },
    })

    rc = update.main(["nitekeeper-atelier"])
    assert rc == 0

    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    mp_atelier = next(
        p for p in marketplace["plugins"] if p["name"] == "nitekeeper-atelier"
    )
    assert mp_atelier["source"]["ref"] == "v2.0.0"
    assert mp_atelier["source"]["sha"] == SHA_ATELIER_NEW
    # And the plugins.json source-of-truth matches.
    plugins = json.loads(plugins_path.read_text(encoding="utf-8"))
    atelier = next(p for p in plugins["plugins"] if p["name"] == "nitekeeper-atelier")
    assert atelier["current_version"] == "v2.0.0"
    assert atelier["current_sha"] == SHA_ATELIER_NEW
