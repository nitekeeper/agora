# scripts/atomic.py
"""Transactional file writes for the agora marketplace tooling.

Provides single-file and atomic-pair writes built on temp file + os.replace.
On Windows, os.replace can fail with PermissionError if another process briefly
holds the destination open; we retry with exponential backoff.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path

_RETRY_DELAYS_MS = (50, 150, 400)


class AtomicWriteError(OSError):
    """Raised when an atomic write fails after all retries."""


def _coerce(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def _write_tmp(target: Path, content: str | bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        mode = "wb"
        kwargs: dict = {}
    else:
        mode = "w"
        kwargs = {"encoding": "utf-8", "newline": ""}
    # delete=False is intentional: the caller renames the tempfile to its
    # final destination atomically (via os.replace), so a context manager
    # auto-cleanup would defeat the whole point.
    fd = tempfile.NamedTemporaryFile(  # noqa: SIM115 - see comment above
        mode=mode,
        delete=False,
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
        **kwargs,
    )
    try:
        with fd as f:
            f.write(content)
        return Path(fd.name)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(fd.name)
        raise


def _replace_with_retry(src: Path, dst: Path) -> None:
    last_err: BaseException | None = None
    for delay_ms in (0, *_RETRY_DELAYS_MS):
        if delay_ms:
            time.sleep(delay_ms / 1000.0)
        try:
            os.replace(str(src), str(dst))
            return
        except PermissionError as e:
            last_err = e
            continue
    raise AtomicWriteError(
        f"os.replace failed after {len(_RETRY_DELAYS_MS)} retries: {src} -> {dst}"
    ) from last_err


def _cleanup(*paths: Path | None) -> None:
    for p in paths:
        if p is None:
            continue
        with contextlib.suppress(OSError):
            os.unlink(str(p))


def atomic_write(path: Path | str, content: str | bytes) -> None:
    """Write content to path via temp file + os.replace."""
    target = _coerce(path)
    tmp = _write_tmp(target, content)
    try:
        _replace_with_retry(tmp, target)
    except BaseException:
        _cleanup(tmp)
        raise


def atomic_write_pair(
    primary_path: Path | str,
    primary_content: str | bytes,
    secondary_path: Path | str,
    secondary_content: str | bytes,
) -> None:
    """Two-file atomic write with cross-file ordering.

    Writes both temp files first (secondary, then primary), then replaces
    primary, then secondary. On any failure, both temp files are cleaned up.
    """
    primary = _coerce(primary_path)
    secondary = _coerce(secondary_path)

    secondary_tmp: Path | None = None
    primary_tmp: Path | None = None
    try:
        secondary_tmp = _write_tmp(secondary, secondary_content)
        primary_tmp = _write_tmp(primary, primary_content)
        _replace_with_retry(primary_tmp, primary)
        primary_tmp = None
        _replace_with_retry(secondary_tmp, secondary)
        secondary_tmp = None
    except BaseException:
        _cleanup(primary_tmp, secondary_tmp)
        raise
