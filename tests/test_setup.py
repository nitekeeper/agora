# tests/test_setup.py
"""Tests for scripts.setup (agora bootstrap)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import paths, setup as agora_setup


SAMPLE_PLUGINS = {
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
            "current_sha": "abc1230000000000000000000000000000000000",
            "description": "Shared workspace methodology",
        },
    ],
}


def _setup_env(tmp_path: Path, monkeypatch, settings_content: str | None = None):
    """Patch paths.* to live entirely under tmp_path.

    Returns (settings_path, repo_root, plugins_path, marketplace_path).
    """
    home = tmp_path / "home"
    home.mkdir()
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    if settings_content is not None:
        settings_path.write_text(settings_content, encoding="utf-8")

    repo_root = tmp_path / "agora-repo"
    repo_root.mkdir()
    (repo_root / ".claude-plugin").mkdir()
    plugins_path = repo_root / "plugins.json"
    marketplace_path = repo_root / ".claude-plugin" / "marketplace.json"
    plugins_path.write_text(
        json.dumps(SAMPLE_PLUGINS, indent=2) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(paths, "CLAUDE_SETTINGS_JSON", settings_path)
    monkeypatch.setattr(paths, "REPO_ROOT", repo_root)
    monkeypatch.setattr(paths, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(paths, "MARKETPLACE_JSON", marketplace_path)
    # compile_to_disk reads its default args at call time from its own module,
    # which captured these paths at import. Patch there too.
    from scripts import compile as compile_module
    monkeypatch.setattr(compile_module, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(compile_module, "MARKETPLACE_JSON", marketplace_path)

    return settings_path, repo_root, plugins_path, marketplace_path


def _expected_agora_path(repo_root: Path) -> str:
    return str(repo_root.resolve()).replace("\\", "/")


# --------------------------------------------------------------------------- 1
def test_first_run_no_existing_settings(tmp_path: Path, monkeypatch, capsys) -> None:
    settings_path, repo_root, _, marketplace_path = _setup_env(tmp_path, monkeypatch)

    rc = agora_setup.run_setup(yes=True)
    assert rc == 0

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["extraKnownMarketplaces"]["agora"] == {
        "source": "directory",
        "path": _expected_agora_path(repo_root),
    }
    assert marketplace_path.exists()
    out = capsys.readouterr().out
    assert "Agora bootstrap complete." in out


# --------------------------------------------------------------------------- 2
def test_existing_unrelated_keys_preserved(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    existing = {"theme": "dark", "model": "opus", "permissions": {"allow": []}}
    settings_path, repo_root, _, _ = _setup_env(
        tmp_path, monkeypatch, json.dumps(existing, indent=2)
    )

    rc = agora_setup.run_setup(yes=True)
    assert rc == 0

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["model"] == "opus"
    assert data["permissions"] == {"allow": []}
    assert data["extraKnownMarketplaces"]["agora"]["path"] == _expected_agora_path(
        repo_root
    )


# --------------------------------------------------------------------------- 3
def test_existing_other_marketplaces_kept(
    tmp_path: Path, monkeypatch
) -> None:
    existing = {
        "extraKnownMarketplaces": {
            "other": {"source": "url", "url": "https://example.com/mkt.json"}
        }
    }
    settings_path, repo_root, _, _ = _setup_env(
        tmp_path, monkeypatch, json.dumps(existing, indent=2)
    )

    rc = agora_setup.run_setup(yes=True)
    assert rc == 0

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    known = data["extraKnownMarketplaces"]
    assert "other" in known
    assert known["other"]["url"] == "https://example.com/mkt.json"
    assert known["agora"]["path"] == _expected_agora_path(repo_root)


# --------------------------------------------------------------------------- 4
def test_already_correct_state_no_changes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # Build a settings.json that already matches what we'd produce.
    # We need to know the repo_root path that will be patched in.
    home = tmp_path / "home"
    home.mkdir()
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    repo_root = tmp_path / "agora-repo"
    repo_root.mkdir()
    (repo_root / ".claude-plugin").mkdir()
    plugins_path = repo_root / "plugins.json"
    marketplace_path = repo_root / ".claude-plugin" / "marketplace.json"
    plugins_path.write_text(
        json.dumps(SAMPLE_PLUGINS, indent=2) + "\n", encoding="utf-8"
    )
    agora_path = str(repo_root.resolve()).replace("\\", "/")
    settings_path.write_text(
        json.dumps(
            {"extraKnownMarketplaces": {"agora": {"source": "directory", "path": agora_path}}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "CLAUDE_SETTINGS_JSON", settings_path)
    monkeypatch.setattr(paths, "REPO_ROOT", repo_root)
    monkeypatch.setattr(paths, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(paths, "MARKETPLACE_JSON", marketplace_path)
    from scripts import compile as compile_module
    monkeypatch.setattr(compile_module, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(compile_module, "MARKETPLACE_JSON", marketplace_path)

    # input() should not be called.
    def _no_input(*_a, **_kw):  # pragma: no cover - defensive
        raise AssertionError("input() should not be called when no changes")
    monkeypatch.setattr("builtins.input", _no_input)

    pre_mtime = settings_path.stat().st_mtime_ns
    pre_size = settings_path.stat().st_size

    rc = agora_setup.run_setup(yes=False)
    out = capsys.readouterr().out
    assert rc == 0
    assert "No changes needed" in out

    # No backup files alongside.
    backups = list(claude_dir.glob("settings.json.bak.*"))
    assert backups == []

    # File contents unchanged (mtime/size as a sanity check).
    assert settings_path.stat().st_size == pre_size


# --------------------------------------------------------------------------- 5
def test_path_mismatch_shown_in_diff(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    existing = {
        "extraKnownMarketplaces": {
            "agora": {"source": "directory", "path": "C:/old/path"}
        }
    }
    settings_path, repo_root, _, _ = _setup_env(
        tmp_path, monkeypatch, json.dumps(existing, indent=2)
    )

    rc = agora_setup.run_setup(yes=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "extraKnownMarketplaces.agora.path" in out
    assert '"C:/old/path"' in out
    assert _expected_agora_path(repo_root) in out

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["extraKnownMarketplaces"]["agora"]["path"] == _expected_agora_path(
        repo_root
    )


# --------------------------------------------------------------------------- 6
def test_confirmation_declined(tmp_path: Path, monkeypatch, capsys) -> None:
    settings_path, _, _, marketplace_path = _setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "n")

    rc = agora_setup.run_setup(yes=False)
    out = capsys.readouterr().out
    assert rc == 0
    assert "cancelled" in out
    assert not settings_path.exists()
    # Marketplace also not compiled when cancelled.
    assert not marketplace_path.exists()


# --------------------------------------------------------------------------- 7
def test_confirmation_accepted(tmp_path: Path, monkeypatch, capsys) -> None:
    settings_path, repo_root, _, _ = _setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "y")

    rc = agora_setup.run_setup(yes=False)
    assert rc == 0
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["extraKnownMarketplaces"]["agora"]["path"] == _expected_agora_path(
        repo_root
    )


# --------------------------------------------------------------------------- 8
def test_yes_flag_skips_prompt(tmp_path: Path, monkeypatch) -> None:
    settings_path, _, _, _ = _setup_env(tmp_path, monkeypatch)

    def _no_input(*_a, **_kw):  # pragma: no cover - defensive
        raise AssertionError("input() must not be called with --yes")
    monkeypatch.setattr("builtins.input", _no_input)

    rc = agora_setup.run_setup(yes=True)
    assert rc == 0
    assert settings_path.exists()


# --------------------------------------------------------------------------- 9
def test_backup_created_when_overwriting(
    tmp_path: Path, monkeypatch
) -> None:
    existing = {"theme": "dark"}
    settings_path, _, _, _ = _setup_env(
        tmp_path, monkeypatch, json.dumps(existing, indent=2)
    )

    rc = agora_setup.run_setup(yes=True)
    assert rc == 0

    backups = list(settings_path.parent.glob("settings.json.bak.*"))
    assert len(backups) == 1
    backup_data = json.loads(backups[0].read_text(encoding="utf-8"))
    # Backup must be the OLD content (before our changes).
    assert backup_data == {"theme": "dark"}


# -------------------------------------------------------------------------- 10
def test_initial_compile_runs(tmp_path: Path, monkeypatch) -> None:
    _setup_env(tmp_path, monkeypatch)

    calls = {"n": 0}
    from scripts import compile as compile_module

    real_compile = compile_module.compile_to_disk

    def _spy(*a, **kw):
        calls["n"] += 1
        return real_compile(*a, **kw)

    monkeypatch.setattr(compile_module, "compile_to_disk", _spy)
    # setup imports the module by alias, so patching the module attribute is enough.
    monkeypatch.setattr(agora_setup.compile_module, "compile_to_disk", _spy)

    rc = agora_setup.run_setup(yes=True)
    assert rc == 0
    assert calls["n"] == 1


# -------------------------------------------------------------------------- 11
def test_malformed_existing_settings(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _setup_env(tmp_path, monkeypatch, "{not valid json")

    with pytest.raises(SystemExit) as exc:
        agora_setup.run_setup(yes=True)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "not valid JSON" in err
