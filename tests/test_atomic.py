# tests/test_atomic.py
"""Tests for scripts.atomic."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import atomic
from scripts.atomic import AtomicWriteError, atomic_write, atomic_write_pair


def _list_tmp(d: Path) -> list[Path]:
    return [p for p in d.iterdir() if p.suffix == ".tmp"]


def test_atomic_write_writes_content(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    atomic_write(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
    assert _list_tmp(tmp_path) == []


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text("old", encoding="utf-8")
    atomic_write(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_accepts_str_and_bytes(tmp_path: Path) -> None:
    str_target = tmp_path / "s.txt"
    bytes_target = tmp_path / "b.bin"
    atomic_write(str_target, "hello")
    atomic_write(bytes_target, b"\x00\x01\x02")
    assert str_target.read_text(encoding="utf-8") == "hello"
    assert bytes_target.read_bytes() == b"\x00\x01\x02"


def test_atomic_write_cleans_up_tmp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.json"

    def boom(src: str, dst: str) -> None:
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(atomic.os, "replace", boom)
    with pytest.raises(RuntimeError, match="disk exploded"):
        atomic_write(target, "data")
    assert not target.exists()
    assert _list_tmp(tmp_path) == []


def test_atomic_write_pair_writes_both(tmp_path: Path) -> None:
    primary = tmp_path / "plugins.json"
    secondary = tmp_path / ".claude-plugin" / "marketplace.json"
    atomic_write_pair(primary, '{"p": 1}', secondary, '{"s": 2}')
    assert primary.read_text(encoding="utf-8") == '{"p": 1}'
    assert secondary.read_text(encoding="utf-8") == '{"s": 2}'
    assert _list_tmp(tmp_path) == []
    assert _list_tmp(secondary.parent) == []


def test_atomic_write_pair_cleans_up_when_second_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = tmp_path / "plugins.json"
    secondary = tmp_path / "marketplace.json"

    real_replace = os.replace
    call_count = {"n": 0}

    def flaky(src: str, dst: str) -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            real_replace(src, dst)
            return
        raise RuntimeError("second replace failed")

    monkeypatch.setattr(atomic.os, "replace", flaky)
    with pytest.raises(RuntimeError, match="second replace failed"):
        atomic_write_pair(primary, "P", secondary, "S")

    # primary got replaced (call 1 succeeded), secondary tmp cleaned up
    assert primary.read_text(encoding="utf-8") == "P"
    assert not secondary.exists()
    assert _list_tmp(tmp_path) == []


def test_atomic_write_pair_leaves_originals_untouched_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = tmp_path / "plugins.json"
    secondary = tmp_path / "marketplace.json"
    primary.write_text("ORIG_P", encoding="utf-8")
    secondary.write_text("ORIG_S", encoding="utf-8")

    def boom(src: str, dst: str) -> None:
        raise RuntimeError("nope")

    monkeypatch.setattr(atomic.os, "replace", boom)
    with pytest.raises(RuntimeError, match="nope"):
        atomic_write_pair(primary, "NEW_P", secondary, "NEW_S")

    assert primary.read_text(encoding="utf-8") == "ORIG_P"
    assert secondary.read_text(encoding="utf-8") == "ORIG_S"
    assert _list_tmp(tmp_path) == []


def test_windows_retry_succeeds_after_two_permission_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.json"
    real_replace = os.replace
    attempts = {"n": 0}

    def flaky(src: str, dst: str) -> None:
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise PermissionError("locked by AV")
        real_replace(src, dst)

    monkeypatch.setattr(atomic.os, "replace", flaky)
    # Speed up the test: no real sleeps
    monkeypatch.setattr(atomic.time, "sleep", lambda _s: None)

    atomic_write(target, "ok")
    assert target.read_text(encoding="utf-8") == "ok"
    assert attempts["n"] == 3
    assert _list_tmp(tmp_path) == []


def test_windows_retry_exhausted_raises_atomic_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.json"

    def always_locked(src: str, dst: str) -> None:
        raise PermissionError("always locked")

    monkeypatch.setattr(atomic.os, "replace", always_locked)
    monkeypatch.setattr(atomic.time, "sleep", lambda _s: None)

    with pytest.raises(AtomicWriteError):
        atomic_write(target, "ok")
    assert not target.exists()
    assert _list_tmp(tmp_path) == []
