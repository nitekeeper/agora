# scripts/license_parser.py
"""SPDX license detection from LICENSE file content.

Inspects the first ~2KB of a license file and matches against a table of
known fingerprints. Honors an explicit SPDX-License-Identifier header when
present.
"""

from __future__ import annotations

import re
from pathlib import Path

_HEAD_BYTES = 2048
_SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.\-+]+)", re.IGNORECASE)


def _has(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack


# (spdx_id, required_phrases, forbidden_phrases)
# Order matters: more specific entries appear before less specific ones.
_FINGERPRINTS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    (
        "MIT",
        ("Permission is hereby granted, free of charge, to any person obtaining a copy",),
        (),
    ),
    (
        "Apache-2.0",
        ("Apache License", "Version 2.0"),
        (),
    ),
    (
        "AGPL-3.0-only",
        ("GNU AFFERO GENERAL PUBLIC LICENSE", "Version 3"),
        (),
    ),
    (
        "LGPL-3.0-only",
        ("GNU LESSER GENERAL PUBLIC LICENSE", "Version 3"),
        (),
    ),
    (
        "LGPL-2.1-only",
        ("GNU LESSER GENERAL PUBLIC LICENSE", "Version 2.1"),
        (),
    ),
    (
        "GPL-3.0-only",
        ("GNU GENERAL PUBLIC LICENSE", "Version 3"),
        (),
    ),
    (
        "GPL-2.0-only",
        ("GNU GENERAL PUBLIC LICENSE", "Version 2"),
        ("Version 3",),
    ),
    (
        "BSD-3-Clause",
        ("Redistribution and use in source and binary forms", "Neither the name of"),
        (),
    ),
    (
        "BSD-2-Clause",
        ("Redistribution and use in source and binary forms",),
        ("Neither the name of",),
    ),
    (
        "MPL-2.0",
        ("Mozilla Public License Version 2.0",),
        (),
    ),
    (
        "ISC",
        ("Permission to use, copy, modify, and/or distribute this software",),
        (),
    ),
    (
        "Unlicense",
        ("This is free and unencumbered software released into the public domain",),
        (),
    ),
    (
        "CC0-1.0",
        ("CC0 1.0 Universal",),
        (),
    ),
]


def detect_spdx(license_text: str) -> str | None:
    if not license_text:
        return None
    head = license_text[:_HEAD_BYTES]
    m = _SPDX_RE.search(head)
    if m:
        token = m.group(1).strip()
        if token:
            return token
    haystack = head.lower()
    for spdx_id, required, forbidden in _FINGERPRINTS:
        if all(_has(haystack, p) for p in required) and not any(
            _has(haystack, p) for p in forbidden
        ):
            return spdx_id
    return None


def detect_spdx_from_file(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8", errors="strict") as f:
            text = f.read(_HEAD_BYTES)
    except (OSError, UnicodeDecodeError):
        return None
    return detect_spdx(text)
