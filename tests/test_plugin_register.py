# tests/test_plugin_register.py
"""Tests for scripts.plugin_register."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from scripts import plugin_register
from scripts.github_api import GitHubAPIError, RepoMetadata
from scripts.plugin_register import RegisterError


# ---------- fixtures ----------


def _seed_plugins_json(tmp_path: Path, plugins: list[dict] | None = None) -> Path:
    plugins_path = tmp_path / "plugins.json"
    data = {
        "$schema": "https://nitekeeper.github.io/agora/plugins.schema.json",
        "marketplace": {
            "name": "agora",
            "description": "Custom Claude Code plugin marketplace",
            "owner": {"name": "nitekeeper"},
        },
        "plugins": plugins or [],
    }
    plugins_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return plugins_path


@pytest.fixture
def reg_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    plugins_path = _seed_plugins_json(tmp_path)
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"
    # registry.save_registry / load_registry use scripts.paths defaults if not
    # overridden, but we pass them explicitly via register(). Still, patch
    # paths for any code that reaches the module-level default.
    monkeypatch.setattr(plugin_register.registry, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(
        plugin_register.registry, "MARKETPLACE_JSON", marketplace_path
    )
    return plugins_path, marketplace_path


def _make_clone_mock(
    license_text: str | None = "MIT License\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy",
    license_name: str = "LICENSE",
) -> Callable[..., Path]:
    def _clone(url: str, tag: str, target_dir, timeout: int = 120) -> Path:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        if license_text is not None:
            (target / license_name).write_text(license_text, encoding="utf-8")
        return target

    return _clone


def _install_default_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tags: dict[str, str] | None = None,
    metadata: RepoMetadata | None = None,
    clone_fn: Callable[..., Path] | None = None,
    local_url: str | None = None,
) -> None:
    if tags is None:
        tags = {"v1.0.0": "a" * 40}
    if metadata is None:
        metadata = RepoMetadata(
            description="A nifty plugin",
            topics=["claude-code", "workflow"],
            homepage="https://example.com/plug",
            license_spdx_id="MIT",
        )
    if clone_fn is None:
        clone_fn = _make_clone_mock()
    monkeypatch.setattr(
        plugin_register.git_helpers, "ls_remote_tags", lambda url, **kw: tags
    )
    monkeypatch.setattr(
        plugin_register.git_helpers, "shallow_clone", clone_fn
    )
    monkeypatch.setattr(
        plugin_register.git_helpers, "get_local_remote_url",
        lambda repo_dir=None: local_url,
    )
    monkeypatch.setattr(
        plugin_register.github_api, "get_repo_metadata",
        lambda owner, repo: metadata,
    )


# ---------- happy paths ----------


def test_register_new_plugin_writes_full_entry(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(monkeypatch)

    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )

    assert entry["name"] == "atelier"
    assert entry["repository_url"] == "https://github.com/nitekeeper/atelier.git"
    assert entry["current_version"] == "v1.0.0"
    assert entry["current_sha"] == "a" * 40
    assert entry["description"] == "A nifty plugin"
    assert entry["license"] == "MIT"
    assert entry["category"] == "development"  # from 'claude-code' topic
    assert entry["keywords"] == ["workflow"]   # category-topic stripped
    assert entry["author"] == {"name": "nitekeeper"}
    assert entry["homepage"] == "https://example.com/plug"
    assert entry["registered_at"].endswith("Z")
    assert entry["updated_at"] == entry["registered_at"]

    # plugins.json updated
    data = json.loads(plugins_path.read_text(encoding="utf-8"))
    assert len(data["plugins"]) == 1
    assert data["plugins"][0] == entry

    # marketplace.json regenerated
    assert marketplace_path.exists()
    market = json.loads(marketplace_path.read_text(encoding="utf-8"))
    assert len(market["plugins"]) == 1
    assert market["plugins"][0]["name"] == "atelier"
    assert market["plugins"][0]["source"]["ref"] == "v1.0.0"


def test_register_existing_plugin_preserves_registered_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old_entry = {
        "name": "atelier",
        "repository_url": "https://github.com/nitekeeper/atelier.git",
        "current_version": "v0.9.0",
        "current_sha": "b" * 40,
        "description": "old desc",
        "license": "MIT",
        "author": {"name": "nitekeeper"},
        "homepage": "https://github.com/nitekeeper/atelier",
        "registered_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-01T00:00:00Z",
    }
    plugins_path = _seed_plugins_json(tmp_path, [old_entry])
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"

    monkeypatch.setattr(plugin_register.registry, "PLUGINS_JSON", plugins_path)
    monkeypatch.setattr(
        plugin_register.registry, "MARKETPLACE_JSON", marketplace_path
    )

    _install_default_mocks(
        monkeypatch,
        tags={"v1.0.0": "c" * 40},
        metadata=RepoMetadata(
            description="A nifty plugin",
            topics=["claude-code"],
            homepage=None,
            license_spdx_id="MIT",
        ),
    )

    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )

    assert entry["current_version"] == "v1.0.0"
    assert entry["current_sha"] == "c" * 40
    assert entry["registered_at"] == "2020-01-01T00:00:00Z"
    assert entry["updated_at"] != "2020-01-01T00:00:00Z"
    assert entry["updated_at"].endswith("Z")

    data = json.loads(plugins_path.read_text(encoding="utf-8"))
    assert len(data["plugins"]) == 1
    assert data["plugins"][0]["registered_at"] == "2020-01-01T00:00:00Z"


def test_register_auto_detects_url_from_cwd(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        local_url="https://github.com/nitekeeper/atelier.git",
    )

    entry = plugin_register.register(
        url=None,
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["name"] == "atelier"


# ---------- error paths ----------


def test_register_errors_when_no_url_and_no_origin(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(monkeypatch, local_url=None)

    with pytest.raises(RegisterError, match="could not detect repository URL"):
        plugin_register.register(
            url=None,
            plugins_path=plugins_path,
            marketplace_path=marketplace_path,
        )


def test_register_errors_when_no_tags(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(monkeypatch, tags={})

    with pytest.raises(RegisterError, match="no release tags"):
        plugin_register.register(
            url="https://github.com/nitekeeper/atelier.git",
            plugins_path=plugins_path,
            marketplace_path=marketplace_path,
        )


def test_register_errors_when_only_prereleases_default_mode(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch, tags={"v1.0.0-rc1": "d" * 40, "v1.0.0-beta": "e" * 40}
    )

    with pytest.raises(RegisterError, match="no stable release tag"):
        plugin_register.register(
            url="https://github.com/nitekeeper/atelier.git",
            plugins_path=plugins_path,
            marketplace_path=marketplace_path,
        )


def test_register_include_prerelease_selects_prerelease(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch, tags={"v1.0.0-rc1": "d" * 40, "v1.0.0-beta": "e" * 40}
    )

    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        include_prerelease=True,
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    # rc1 > beta per semver pre-release ordering (alphabetical 'rc' > 'beta')
    assert entry["current_version"] == "v1.0.0-rc1"


def test_register_license_falls_back_to_github_api(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    # clone produces no LICENSE file
    _install_default_mocks(
        monkeypatch,
        clone_fn=_make_clone_mock(license_text=None),
        metadata=RepoMetadata(
            description="ok",
            topics=[],
            homepage=None,
            license_spdx_id="Apache-2.0",
        ),
    )
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["license"] == "Apache-2.0"


def test_register_errors_when_license_missing_both_ways(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        clone_fn=_make_clone_mock(license_text=None),
        metadata=RepoMetadata(
            description="ok",
            topics=[],
            homepage=None,
            license_spdx_id="NOASSERTION",
        ),
    )
    with pytest.raises(RegisterError, match="could not determine license"):
        plugin_register.register(
            url="https://github.com/nitekeeper/atelier.git",
            plugins_path=plugins_path,
            marketplace_path=marketplace_path,
        )


def test_register_errors_when_description_empty(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        metadata=RepoMetadata(
            description=None,
            topics=[],
            homepage=None,
            license_spdx_id="MIT",
        ),
    )
    with pytest.raises(RegisterError, match="description is empty"):
        plugin_register.register(
            url="https://github.com/nitekeeper/atelier.git",
            plugins_path=plugins_path,
            marketplace_path=marketplace_path,
        )


def test_register_description_override(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        metadata=RepoMetadata(
            description="", topics=[], homepage=None, license_spdx_id="MIT"
        ),
    )
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        description_override="explicit desc",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["description"] == "explicit desc"


def test_register_category_mapping_first_match_wins(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        metadata=RepoMetadata(
            description="x",
            topics=["unrelated", "data", "figma"],
            homepage=None,
            license_spdx_id="MIT",
        ),
    )
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["category"] == "data"
    # Category-topic ('data') stripped from keywords; 'unrelated' and 'figma' kept.
    assert entry["keywords"] == ["unrelated", "figma"]


def test_register_category_omitted_when_no_topic_maps(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        metadata=RepoMetadata(
            description="x",
            topics=["foo", "bar"],
            homepage=None,
            license_spdx_id="MIT",
        ),
    )
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert "category" not in entry
    assert entry["keywords"] == ["foo", "bar"]


def test_register_category_override_honored(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        metadata=RepoMetadata(
            description="x",
            topics=["data"],
            homepage=None,
            license_spdx_id="MIT",
        ),
    )
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        category_override="other",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["category"] == "other"
    # Override path doesn't strip any topic — 'data' stays in keywords.
    assert "data" in entry["keywords"]


def test_register_invalid_category_override(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(monkeypatch)
    with pytest.raises(RegisterError, match="invalid --category"):
        plugin_register.register(
            url="https://github.com/nitekeeper/atelier.git",
            category_override="bogus",
            plugins_path=plugins_path,
            marketplace_path=marketplace_path,
        )


def test_register_keywords_dedupe_and_cap(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    topics = [f"kw{i}" for i in range(20)] + ["kw0"]  # duplicates and many
    _install_default_mocks(
        monkeypatch,
        metadata=RepoMetadata(
            description="x",
            topics=topics,
            homepage=None,
            license_spdx_id="MIT",
        ),
    )
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert len(entry["keywords"]) == 16
    assert len(set(entry["keywords"])) == 16


def test_register_plugin_name_lowercased(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(monkeypatch)
    entry = plugin_register.register(
        url="https://github.com/Nitekeeper/Atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["name"] == "atelier"


def test_register_homepage_defaults_to_github(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(
        monkeypatch,
        metadata=RepoMetadata(
            description="x", topics=[], homepage=None, license_spdx_id="MIT"
        ),
    )
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier.git",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["homepage"] == "https://github.com/nitekeeper/atelier"


def test_register_github_api_failure_surfaces(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(monkeypatch)

    def _boom(owner: str, repo: str) -> RepoMetadata:
        raise GitHubAPIError("network error: down", status=None)

    # First call (license fallback) returns valid via default LICENSE file,
    # but we need second call (metadata) to fail. Re-patch after the local
    # license file IS present, so license resolution doesn't even consult GH.
    monkeypatch.setattr(
        plugin_register.github_api, "get_repo_metadata", _boom
    )
    with pytest.raises(RegisterError, match="GitHub API request failed"):
        plugin_register.register(
            url="https://github.com/nitekeeper/atelier.git",
            plugins_path=plugins_path,
            marketplace_path=marketplace_path,
        )


def test_register_url_without_git_suffix_normalized(
    monkeypatch: pytest.MonkeyPatch, reg_paths: tuple[Path, Path]
) -> None:
    plugins_path, marketplace_path = reg_paths
    _install_default_mocks(monkeypatch)
    entry = plugin_register.register(
        url="https://github.com/nitekeeper/atelier",
        plugins_path=plugins_path,
        marketplace_path=marketplace_path,
    )
    assert entry["repository_url"] == "https://github.com/nitekeeper/atelier.git"
