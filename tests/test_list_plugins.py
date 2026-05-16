# tests/test_list_plugins.py
"""Tests for scripts.list_plugins (agora:list)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import list_plugins

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
            "current_sha": "abc123",
            "description": "Shared workspace methodology",
            "license": "MIT",
            "category": "development",
        },
        {
            "name": "memex",
            "repository_url": "https://github.com/nitekeeper/memex.git",
            "current_version": "v0.3.1",
            "current_sha": "def456",
            "description": "Memory layer",
            "license": "Apache-2.0",
            "category": "productivity",
        },
    ],
}

EMPTY_PLUGINS = {
    "marketplace": {"name": "agora", "owner": {"name": "nitekeeper"}},
    "plugins": [],
}


def _write_plugins(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "plugins.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _write_cache(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "check-cache.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _run(monkeypatch, *args, isatty: bool = False) -> int:
    """Run list_plugins.main with isatty controlled."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: isatty)
    return list_plugins.main(list(args))


# --------------------------------------------------------------------------- 1
def test_default_two_plugins(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = tmp_path / "missing-cache.json"

    rc = _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
    )
    out = capsys.readouterr().out

    assert rc == 0
    # Header is present, plain (no ANSI when isatty False)
    assert "NAME" in out
    assert "VERSION" in out
    assert "LICENSE" in out
    assert "CATEGORY" in out
    # Both rows
    assert "atelier" in out
    assert "v1.0.0" in out
    assert "MIT" in out
    assert "development" in out
    assert "memex" in out
    assert "Apache-2.0" in out
    assert "productivity" in out


# --------------------------------------------------------------------------- 2
def test_default_empty(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, EMPTY_PLUGINS)
    cache_path = tmp_path / "missing.json"

    rc = _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "(no plugins registered)" in out


# --------------------------------------------------------------------------- 3
def test_json_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    rc = _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--json",
    )
    out = capsys.readouterr().out

    assert rc == 0
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "atelier"
    assert parsed[1]["name"] == "memex"
    # Should NOT have check augmentation keys
    assert "status" not in parsed[0]


# --------------------------------------------------------------------------- 4
def test_json_mode_empty(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, EMPTY_PLUGINS)
    rc = _run(monkeypatch, "--plugins", str(plugins_path), "--json")
    out = capsys.readouterr().out

    assert rc == 0
    assert json.loads(out) == []


# --------------------------------------------------------------------------- 5
def test_check_with_populated_cache(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = _write_cache(
        tmp_path,
        {
            "fetched_at": "2026-05-15T19:00:00Z",
            "plugins": {
                "atelier": {
                    "latest_version": "v1.3.0",
                    "checked_at": "2026-05-15T18:55:00Z",
                },
                "memex": {
                    "latest_version": "v0.3.1",
                    "checked_at": "2026-05-15T18:55:00Z",
                },
            },
        },
    )

    rc = _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
        "--check",
    )
    captured = capsys.readouterr()
    out = captured.out

    assert rc == 0
    assert "CURRENT" in out
    assert "LATEST" in out
    assert "STATUS" in out
    # atelier: outdated
    atelier_line = next(line for line in out.splitlines() if "atelier" in line)
    assert "v1.3.0" in atelier_line
    assert "outdated" in atelier_line
    # memex: up-to-date
    memex_line = next(line for line in out.splitlines() if "memex" in line)
    assert "v0.3.1" in memex_line
    assert "up-to-date" in memex_line


# --------------------------------------------------------------------------- 5b
def test_check_unknown_when_plugin_missing_from_cache(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = _write_cache(
        tmp_path,
        {
            "fetched_at": "2026-05-15T19:00:00Z",
            "plugins": {
                "atelier": {
                    "latest_version": "v1.0.0",
                    "checked_at": "2026-05-15T18:55:00Z",
                },
                # memex absent
            },
        },
    )

    _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
        "--check",
    )
    out = capsys.readouterr().out

    atelier_line = next(line for line in out.splitlines() if "atelier" in line)
    assert "up-to-date" in atelier_line
    memex_line = next(line for line in out.splitlines() if "memex" in line)
    assert "unknown" in memex_line


# --------------------------------------------------------------------------- 6
def test_check_with_missing_cache_warns_and_marks_unknown(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = tmp_path / "does-not-exist.json"

    rc = _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
        "--check",
    )
    captured = capsys.readouterr()

    assert rc == 0
    # Warning on stderr
    assert "cache not found" in captured.err
    assert "scripts/check.py" in captured.err
    # All rows marked unknown on stdout
    out_lines = [line for line in captured.out.splitlines() if "nitekeeper" in line]
    assert all("unknown" in line for line in out_lines)


# --------------------------------------------------------------------------- 7
def test_check_json_includes_latest_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = _write_cache(
        tmp_path,
        {
            "fetched_at": "2026-05-15T19:00:00Z",
            "plugins": {
                "atelier": {
                    "latest_version": "v1.3.0",
                    "checked_at": "2026-05-15T18:55:00Z",
                },
            },
        },
    )

    rc = _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
        "--check",
        "--json",
    )
    out = capsys.readouterr().out

    assert rc == 0
    parsed = json.loads(out)
    assert len(parsed) == 2
    atelier = next(p for p in parsed if p["name"] == "atelier")
    memex = next(p for p in parsed if p["name"] == "memex")
    assert atelier["latest_version"] == "v1.3.0"
    assert atelier["status"] == "outdated"
    assert memex["status"] == "unknown"


# --------------------------------------------------------------------------- 8
def test_missing_plugins_json_exits_1(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = tmp_path / "does-not-exist.json"
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, "--plugins", str(plugins_path))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "not found" in err
    assert "plugins.json" in err


# --------------------------------------------------------------------------- 9
def test_malformed_plugins_json_exits_1(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = tmp_path / "plugins.json"
    plugins_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, "--plugins", str(plugins_path))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "malformed" in err


# --------------------------------------------------------------------------- 10
def test_no_ansi_when_not_tty(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = tmp_path / "missing.json"

    _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
        isatty=False,
    )
    out = capsys.readouterr().out
    assert "\x1b[" not in out


def test_ansi_when_tty(tmp_path: Path, monkeypatch, capsys) -> None:
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = tmp_path / "missing.json"

    _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
        isatty=True,
    )
    out = capsys.readouterr().out
    assert "\x1b[1m" in out
    assert "\x1b[0m" in out


def test_outdated_alias(tmp_path: Path, monkeypatch, capsys) -> None:
    """--outdated should behave identically to --check."""
    plugins_path = _write_plugins(tmp_path, SAMPLE_PLUGINS)
    cache_path = _write_cache(
        tmp_path,
        {
            "fetched_at": "2026-05-15T19:00:00Z",
            "plugins": {
                "atelier": {
                    "latest_version": "v1.3.0",
                    "checked_at": "2026-05-15T18:55:00Z",
                },
            },
        },
    )

    rc = _run(
        monkeypatch,
        "--plugins",
        str(plugins_path),
        "--cache",
        str(cache_path),
        "--outdated",
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "STATUS" in out
    assert "outdated" in out
