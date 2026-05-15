# tests/test_session_start_hook.py
"""Tests for hooks/session_start.py."""
from __future__ import annotations

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
    """Redirect PLUGINS_JSON and MARKETPLACE_JSON into a tmp dir."""
    plugins = tmp_path / "plugins.json"
    marketplace = tmp_path / ".claude-plugin" / "marketplace.json"
    monkeypatch.setattr(paths, "PLUGINS_JSON", plugins)
    monkeypatch.setattr(paths, "MARKETPLACE_JSON", marketplace)
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
