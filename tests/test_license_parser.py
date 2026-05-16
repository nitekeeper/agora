# tests/test_license_parser.py
"""Tests for scripts.license_parser."""

from __future__ import annotations

from pathlib import Path

from scripts.license_parser import detect_spdx, detect_spdx_from_file

MIT_SNIPPET = """MIT License

Copyright (c) 2026 Example

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software.
"""

APACHE_SNIPPET = """                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
"""

GPL3_SNIPPET = """                    GNU GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc.
"""

GPL2_SNIPPET = """                    GNU GENERAL PUBLIC LICENSE
                       Version 2, June 1991

 Copyright (C) 1989, 1991 Free Software Foundation, Inc.
"""

LGPL3_SNIPPET = """                   GNU LESSER GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc.
"""

LGPL21_SNIPPET = """                  GNU LESSER GENERAL PUBLIC LICENSE
                       Version 2.1, February 1999

 Copyright (C) 1991, 1999 Free Software Foundation, Inc.
"""

AGPL3_SNIPPET = """                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007

 Copyright (C) 2007 Free Software Foundation, Inc.
"""

BSD3_SNIPPET = """Copyright (c) 2026, Example
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice.
2. Redistributions in binary form must reproduce the above copyright notice.
3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.
"""

BSD2_SNIPPET = """Copyright (c) 2026, Example
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice.
2. Redistributions in binary form must reproduce the above copyright notice.
"""

ISC_SNIPPET = """ISC License

Copyright (c) 2026 Example

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.
"""

MPL_SNIPPET = """Mozilla Public License Version 2.0
==================================

1. Definitions
--------------
"""

UNLICENSE_SNIPPET = """This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software.
"""

CC0_SNIPPET = """Creative Commons CC0 1.0 Universal

Statement of Purpose

The laws of most jurisdictions throughout the world automatically confer
exclusive Copyright and Related Rights.
"""


def test_detect_mit() -> None:
    assert detect_spdx(MIT_SNIPPET) == "MIT"


def test_detect_apache_2_0() -> None:
    assert detect_spdx(APACHE_SNIPPET) == "Apache-2.0"


def test_detect_gpl_3_0() -> None:
    assert detect_spdx(GPL3_SNIPPET) == "GPL-3.0-only"


def test_detect_gpl_2_0() -> None:
    assert detect_spdx(GPL2_SNIPPET) == "GPL-2.0-only"


def test_detect_lgpl_3_0() -> None:
    assert detect_spdx(LGPL3_SNIPPET) == "LGPL-3.0-only"


def test_detect_lgpl_2_1() -> None:
    assert detect_spdx(LGPL21_SNIPPET) == "LGPL-2.1-only"


def test_detect_agpl_3_0() -> None:
    assert detect_spdx(AGPL3_SNIPPET) == "AGPL-3.0-only"


def test_detect_bsd_3_clause() -> None:
    assert detect_spdx(BSD3_SNIPPET) == "BSD-3-Clause"


def test_detect_bsd_2_clause() -> None:
    assert detect_spdx(BSD2_SNIPPET) == "BSD-2-Clause"


def test_detect_isc() -> None:
    assert detect_spdx(ISC_SNIPPET) == "ISC"


def test_detect_mpl_2_0() -> None:
    assert detect_spdx(MPL_SNIPPET) == "MPL-2.0"


def test_detect_unlicense() -> None:
    assert detect_spdx(UNLICENSE_SNIPPET) == "Unlicense"


def test_detect_cc0_1_0() -> None:
    assert detect_spdx(CC0_SNIPPET) == "CC0-1.0"


def test_empty_string_returns_none() -> None:
    assert detect_spdx("") is None


def test_unrelated_text_returns_none() -> None:
    assert detect_spdx("This is a recipe for soup.") is None


def test_spdx_header_only() -> None:
    assert detect_spdx("SPDX-License-Identifier: Apache-2.0\n") == "Apache-2.0"


def test_spdx_header_overrides_body() -> None:
    text = "SPDX-License-Identifier: Apache-2.0\n\n" + MIT_SNIPPET
    assert detect_spdx(text) == "Apache-2.0"


def test_detect_spdx_from_file_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "LICENSE"
    p.write_text(MIT_SNIPPET, encoding="utf-8")
    assert detect_spdx_from_file(p) == "MIT"


def test_detect_spdx_from_file_missing_returns_none(tmp_path: Path) -> None:
    assert detect_spdx_from_file(tmp_path / "NOPE") is None


def test_detect_spdx_from_file_binary_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "LICENSE.bin"
    p.write_bytes(b"\x00\x01\x02\xff\xfe\xfd" + b"\x80" * 64)
    assert detect_spdx_from_file(p) is None


def test_gpl_disambiguation() -> None:
    assert detect_spdx(GPL2_SNIPPET) == "GPL-2.0-only"
    assert detect_spdx(GPL3_SNIPPET) == "GPL-3.0-only"
