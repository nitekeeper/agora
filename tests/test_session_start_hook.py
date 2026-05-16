# tests/test_session_start_hook.py
"""Tests for hooks/session_start.py."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# The hook lives in hooks/, not scripts/. Add it to sys.path so we can import it.
HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import session_start  # noqa: E402

from scripts import compile as compile_mod  # noqa: E402
from scripts import paths  # noqa: E402


def _touch(path: Path, content: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _set_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


@pytest.fixture
def fake_paths(tmp_path, monkeypatch):
    """Redirect PLUGINS_JSON, MARKETPLACE_JSON and CHECK_CACHE_JSON into a tmp dir."""
    plugins = tmp_path / "plugins.json"
    marketplace = tmp_path / ".claude-plugin" / "marketplace.json"
    cache = tmp_path / "agora-home" / "check-cache.json"
    monkeypatch.setattr(paths, "PLUGINS_JSON", plugins)
    monkeypatch.setattr(paths, "MARKETPLACE_JSON", marketplace)
    monkeypatch.setattr(paths, "CHECK_CACHE_JSON", cache)
    return plugins, marketplace


@pytest.fixture
def compile_spy(monkeypatch):
    """Replace compile_to_disk with a counter; assert call_count in tests."""

    calls = {"count": 0}

    def fake_compile_to_disk(*args, **kwargs):
        calls["count"] += 1
        return {}

    monkeypatch.setattr(compile_mod, "compile_to_disk", fake_compile_to_disk)
    # session_start imported the `compile` module by name; the attribute lookup
    # `compile.compile_to_disk` resolves through that module, so patching
    # `scripts.compile.compile_to_disk` is sufficient.
    return calls


def test_plugins_missing_is_noop(fake_paths, compile_spy):
    """If plugins.json doesn't exist, hook is a no-op."""
    plugins, marketplace = fake_paths
    assert not plugins.exists()

    rc = session_start.main()

    assert rc == 0
    assert compile_spy["count"] == 0


def test_marketplace_missing_triggers_compile(fake_paths, compile_spy):
    """If marketplace.json is missing but plugins.json exists, recompile."""
    plugins, marketplace = fake_paths
    _touch(plugins)
    assert not marketplace.exists()

    rc = session_start.main()

    assert rc == 0
    assert compile_spy["count"] == 1


def test_marketplace_older_triggers_compile(fake_paths, compile_spy):
    """If marketplace.json mtime < plugins.json mtime, recompile."""
    plugins, marketplace = fake_paths
    _touch(plugins)
    _touch(marketplace)
    _set_mtime(marketplace, 1000.0)
    _set_mtime(plugins, 2000.0)

    rc = session_start.main()

    assert rc == 0
    assert compile_spy["count"] == 1


def test_marketplace_newer_is_noop(fake_paths, compile_spy):
    """If marketplace.json mtime > plugins.json mtime, no recompile."""
    plugins, marketplace = fake_paths
    _touch(plugins)
    _touch(marketplace)
    _set_mtime(plugins, 1000.0)
    _set_mtime(marketplace, 2000.0)

    rc = session_start.main()

    assert rc == 0
    assert compile_spy["count"] == 0


def test_equal_mtimes_is_noop(fake_paths, compile_spy):
    """Equal mtimes should be treated as up-to-date (no recompile)."""
    plugins, marketplace = fake_paths
    _touch(plugins)
    _touch(marketplace)
    _set_mtime(plugins, 1500.0)
    _set_mtime(marketplace, 1500.0)

    rc = session_start.main()

    assert rc == 0
    assert compile_spy["count"] == 0


def test_compile_exception_is_swallowed(fake_paths, monkeypatch, capsys):
    """If compile_to_disk raises, hook prints to stderr and still returns 0."""
    plugins, marketplace = fake_paths
    _touch(plugins)

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(compile_mod, "compile_to_disk", boom)

    rc = session_start.main()

    assert rc == 0
    captured = capsys.readouterr()
    assert "agora session-start hook" in captured.err
    assert "kaboom" in captured.err


def test_main_returns_zero_even_on_internal_failure(fake_paths, monkeypatch):
    """main() must always return 0, even if check_staleness blows up internally."""
    plugins, marketplace = fake_paths
    _touch(plugins)

    # Force a failure deep inside check_staleness by making stat() raise.
    def bad_stat(self):
        raise OSError("stat denied")

    monkeypatch.setattr(Path, "stat", bad_stat)

    rc = session_start.main()

    assert rc == 0


# ---------------------------------------------------------------------------
# show_update_banner() tests
# ---------------------------------------------------------------------------


def _write_plugins(plugins_path: Path, entries: list[dict]) -> None:
    _touch(plugins_path, json.dumps({"plugins": entries}))


def _write_cache(cache_path: Path, plugins: dict, fetched_at: str = "2026-05-15T19:00:00Z") -> None:
    payload = {
        "fetched_at": fetched_at,
        "include_prerelease": False,
        "plugins": plugins,
    }
    _touch(cache_path, json.dumps(payload))


def test_banner_no_cache_is_silent(fake_paths, capsys):
    """If check-cache.json is missing, banner is silent."""
    plugins, _ = fake_paths
    _write_plugins(plugins, [{"name": "atelier", "current_version": "v1.0.0"}])

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_banner_malformed_cache_is_silent(fake_paths, capsys):
    """If cache JSON is malformed, banner is silent."""
    plugins, _ = fake_paths
    _write_plugins(plugins, [{"name": "atelier", "current_version": "v1.0.0"}])
    _touch(paths.CHECK_CACHE_JSON, "{not valid json")

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_banner_no_plugins_json_is_silent(fake_paths, capsys):
    """If plugins.json is missing, banner is silent."""
    _write_cache(paths.CHECK_CACHE_JSON, {"atelier": {"latest_version": "v1.3.0"}})

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_banner_malformed_plugins_json_is_silent(fake_paths, capsys):
    """If plugins.json is malformed, banner is silent."""
    plugins, _ = fake_paths
    _touch(plugins, "{not valid json")
    _write_cache(paths.CHECK_CACHE_JSON, {"atelier": {"latest_version": "v1.3.0"}})

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_banner_lists_only_outdated_plugins(fake_paths, capsys):
    """Banner lists plugins where latest differs from current; skips up-to-date ones."""
    plugins, _ = fake_paths
    _write_plugins(
        plugins,
        [
            {"name": "atelier", "current_version": "v1.0.0"},
            {"name": "memex", "current_version": "v0.3.0"},
            {"name": "uptodate", "current_version": "v2.0.0"},
        ],
    )
    _write_cache(
        paths.CHECK_CACHE_JSON,
        {
            "atelier": {"latest_version": "v1.3.0", "checked_at": "x"},
            "memex": {"latest_version": "v0.4.0", "checked_at": "x"},
            "uptodate": {"latest_version": "v2.0.0", "checked_at": "x"},
        },
    )

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert "Plugin updates available:" in captured.out
    assert "atelier" in captured.out
    assert "memex" in captured.out
    assert "uptodate" not in captured.out
    assert "v1.0.0 -> v1.3.0" in captured.out
    assert "v0.3.0 -> v0.4.0" in captured.out
    assert "agora:update --all" in captured.out


def test_banner_all_up_to_date_is_silent(fake_paths, capsys):
    """If everything is current, banner is silent."""
    plugins, _ = fake_paths
    _write_plugins(plugins, [{"name": "atelier", "current_version": "v1.0.0"}])
    _write_cache(paths.CHECK_CACHE_JSON, {"atelier": {"latest_version": "v1.0.0"}})

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert captured.out == ""


def test_banner_skips_plugin_with_null_latest(fake_paths, capsys):
    """Cache entries with null latest_version (errored) are skipped."""
    plugins, _ = fake_paths
    _write_plugins(
        plugins,
        [
            {"name": "atelier", "current_version": "v1.0.0"},
            {"name": "errored", "current_version": "v0.3.0"},
        ],
    )
    _write_cache(
        paths.CHECK_CACHE_JSON,
        {
            "atelier": {"latest_version": "v1.3.0"},
            "errored": {"latest_version": None, "error": "ls-remote failed"},
        },
    )

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert "atelier" in captured.out
    assert "errored" not in captured.out


def test_banner_skips_plugin_not_in_cache(fake_paths, capsys):
    """Plugins listed in plugins.json but absent from cache are skipped silently."""
    plugins, _ = fake_paths
    _write_plugins(
        plugins,
        [
            {"name": "atelier", "current_version": "v1.0.0"},
            {"name": "uncached", "current_version": "v0.1.0"},
        ],
    )
    _write_cache(
        paths.CHECK_CACHE_JSON,
        {"atelier": {"latest_version": "v1.3.0"}},
    )

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert "atelier" in captured.out
    assert "uncached" not in captured.out


def test_banner_ignores_stale_cache_rows(fake_paths, capsys):
    """Cache entries for plugins no longer in plugins.json are ignored."""
    plugins, _ = fake_paths
    _write_plugins(plugins, [{"name": "atelier", "current_version": "v1.0.0"}])
    _write_cache(
        paths.CHECK_CACHE_JSON,
        {
            "atelier": {"latest_version": "v1.3.0"},
            "removed": {"latest_version": "v9.9.9"},
        },
    )

    session_start.show_update_banner()

    captured = capsys.readouterr()
    assert "atelier" in captured.out
    assert "removed" not in captured.out


def test_banner_aligns_columns_by_max_name_width(fake_paths, capsys):
    """Plugin name column is padded to the width of the longest outdated name."""
    plugins, _ = fake_paths
    _write_plugins(
        plugins,
        [
            {"name": "short", "current_version": "v1.0.0"},
            {"name": "much-much-longer-name", "current_version": "v0.3.0"},
        ],
    )
    _write_cache(
        paths.CHECK_CACHE_JSON,
        {
            "short": {"latest_version": "v1.1.0"},
            "much-much-longer-name": {"latest_version": "v0.4.0"},
        },
    )

    session_start.show_update_banner()

    captured = capsys.readouterr()
    out = captured.out
    width = len("much-much-longer-name")
    # The short name must be left-justified to the long-name width.
    assert f"  {'short'.ljust(width)}  v1.0.0 -> v1.1.0" in out
    assert f"  {'much-much-longer-name'.ljust(width)}  v0.3.0 -> v0.4.0" in out


def test_banner_swallows_unexpected_exception(fake_paths, monkeypatch, capsys):
    """A corrupt cache structure causing an exception is caught; stderr warning emitted."""
    plugins, _ = fake_paths
    _write_plugins(plugins, [{"name": "atelier", "current_version": "v1.0.0"}])
    # cache "plugins" is a list rather than a dict — entry lookup will go wrong
    # downstream. Force a corrupt structure by writing an unexpected top-level type.
    _touch(paths.CHECK_CACHE_JSON, json.dumps({"plugins": "not-a-dict"}))

    rc = session_start.main()

    assert rc == 0
    captured = capsys.readouterr()
    assert "agora session-start banner" in captured.err


def test_main_calls_both_functions(fake_paths, monkeypatch):
    """main() invokes check_staleness AND show_update_banner."""
    plugins, _ = fake_paths
    _touch(plugins)

    calls: list[str] = []

    def fake_check():
        calls.append("check")

    def fake_banner():
        calls.append("banner")

    monkeypatch.setattr(session_start, "check_staleness", fake_check)
    monkeypatch.setattr(session_start, "show_update_banner", fake_banner)

    rc = session_start.main()

    assert rc == 0
    assert calls == ["check", "banner"]
