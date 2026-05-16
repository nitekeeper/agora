# scripts/semver.py
"""SemVer tag parsing, comparison, and selection.

Strict MAJOR.MINOR.PATCH with optional -PRERELEASE; +BUILDMETADATA is parsed
but discarded. Tags may have a leading 'v' which is stripped on parse but
preserved by pick_latest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import total_ordering

_TAG_RE = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)"
    r"(?:-([0-9A-Za-z.-]+))?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)
_IDENT_RE = re.compile(r"^[0-9A-Za-z-]+$")


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str | int, ...] | None = field(default=None)

    def _core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self._core() != other._core():
            return self._core() < other._core()
        if self.prerelease is None and other.prerelease is None:
            return False
        if self.prerelease is None:
            return False
        if other.prerelease is None:
            return True
        return _cmp_prerelease(self.prerelease, other.prerelease) < 0


def _parse_prerelease(raw: str) -> tuple[str | int, ...] | None:
    if not raw:
        return None
    parts: list[str | int] = []
    for ident in raw.split("."):
        if not ident or not _IDENT_RE.match(ident):
            return None
        if ident.isdigit():
            if len(ident) > 1 and ident.startswith("0"):
                return None
            parts.append(int(ident))
        else:
            parts.append(ident)
    return tuple(parts)


def _cmp_ident(a: str | int, b: str | int) -> int:
    a_num = isinstance(a, int)
    b_num = isinstance(b, int)
    if a_num and b_num:
        return (a > b) - (a < b)  # type: ignore[operator]
    if a_num and not b_num:
        return -1
    if b_num and not a_num:
        return 1
    return (a > b) - (a < b)  # type: ignore[operator]


def _cmp_prerelease(a: tuple[str | int, ...], b: tuple[str | int, ...]) -> int:
    for ai, bi in zip(a, b):
        c = _cmp_ident(ai, bi)
        if c != 0:
            return c
    if len(a) == len(b):
        return 0
    return -1 if len(a) < len(b) else 1


def parse(tag: str) -> Version | None:
    if not isinstance(tag, str) or not tag:
        return None
    m = _TAG_RE.match(tag)
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    prerelease: tuple[str | int, ...] | None = None
    if pre is not None:
        prerelease = _parse_prerelease(pre)
        if prerelease is None:
            return None
    return Version(int(major), int(minor), int(patch), prerelease)


def compare(a: Version, b: Version) -> int:
    if a < b:
        return -1
    if b < a:
        return 1
    return 0


def pick_latest(tags: list[str], include_prerelease: bool = False) -> str | None:
    best_tag: str | None = None
    best_ver: Version | None = None
    for tag in tags:
        ver = parse(tag)
        if ver is None:
            continue
        if not include_prerelease and ver.prerelease is not None:
            continue
        if best_ver is None or best_ver < ver:
            best_ver = ver
            best_tag = tag
    return best_tag
