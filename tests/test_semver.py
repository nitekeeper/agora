# tests/test_semver.py
from __future__ import annotations

import pytest

from scripts.semver import Version, compare, parse, pick_latest


class TestParseStable:
    @pytest.mark.parametrize(
        "tag,expected",
        [
            ("v1.0.0", Version(1, 0, 0, None)),
            ("1.0.0", Version(1, 0, 0, None)),
            ("v1.2.3", Version(1, 2, 3, None)),
            ("v0.0.1", Version(0, 0, 1, None)),
        ],
    )
    def test_stable(self, tag: str, expected: Version) -> None:
        assert parse(tag) == expected


class TestParsePrerelease:
    @pytest.mark.parametrize(
        "tag,prerelease",
        [
            ("v1.0.0-alpha", ("alpha",)),
            ("v1.0.0-rc.1", ("rc", 1)),
            ("v1.0.0-beta.3", ("beta", 3)),
            ("v0.1.0-alpha.1", ("alpha", 1)),
        ],
    )
    def test_prerelease(self, tag: str, prerelease: tuple) -> None:
        v = parse(tag)
        assert v is not None
        assert v.prerelease == prerelease


class TestParseInvalid:
    @pytest.mark.parametrize(
        "tag", ["foo", "v1", "v1.2", "1.2.x", "", "v1.2.3.4"]
    )
    def test_invalid(self, tag: str) -> None:
        assert parse(tag) is None


def test_parse_strips_build_metadata() -> None:
    v = parse("v1.0.0+sha.abc")
    assert v == Version(1, 0, 0, None)


def test_parse_prerelease_with_build_metadata() -> None:
    v = parse("v1.0.0-rc.1+sha.abc")
    assert v is not None
    assert v.prerelease == ("rc", 1)


class TestCompareStable:
    def test_stable_ordering(self) -> None:
        a = parse("v1.0.0")
        b = parse("v1.0.1")
        c = parse("v1.1.0")
        d = parse("v2.0.0")
        assert a and b and c and d
        assert compare(a, b) == -1
        assert compare(b, c) == -1
        assert compare(c, d) == -1
        assert compare(d, a) == 1
        assert compare(a, a) == 0


def test_stable_greater_than_prerelease() -> None:
    rc = parse("v1.0.0-rc.1")
    stable = parse("v1.0.0")
    assert rc and stable
    assert compare(rc, stable) == -1
    assert compare(stable, rc) == 1


def test_prerelease_precedence_canonical() -> None:
    chain = [
        "v1.0.0-alpha",
        "v1.0.0-alpha.1",
        "v1.0.0-alpha.beta",
        "v1.0.0-beta",
        "v1.0.0-beta.2",
        "v1.0.0-beta.11",
        "v1.0.0-rc.1",
    ]
    versions = [parse(t) for t in chain]
    assert all(v is not None for v in versions)
    for i in range(len(versions) - 1):
        assert compare(versions[i], versions[i + 1]) == -1, (
            f"{chain[i]} should be < {chain[i + 1]}"
        )


class TestPickLatest:
    def test_basic_stable(self) -> None:
        assert pick_latest(["v1.0.0", "v1.2.0", "v1.1.0"]) == "v1.2.0"

    def test_skips_prerelease_by_default(self) -> None:
        assert pick_latest(["v1.0.0", "v2.0.0-rc.1"]) == "v1.0.0"

    def test_include_prerelease(self) -> None:
        result = pick_latest(
            ["v1.0.0", "v2.0.0-rc.1"], include_prerelease=True
        )
        assert result == "v2.0.0-rc.1"

    def test_empty_list(self) -> None:
        assert pick_latest([]) is None

    def test_all_garbage(self) -> None:
        assert pick_latest(["garbage", "foo"]) is None

    def test_only_prereleases_default(self) -> None:
        result = pick_latest(
            ["v1.0.0-rc.1", "v0.9.0-beta"], include_prerelease=False
        )
        assert result is None

    def test_preserves_v_prefix(self) -> None:
        assert pick_latest(["1.0.0", "v1.2.0"]) == "v1.2.0"

    def test_preserves_no_v_prefix(self) -> None:
        assert pick_latest(["1.0.0", "1.2.0"]) == "1.2.0"

    def test_silently_skips_invalid_tags(self) -> None:
        assert pick_latest(["garbage", "v1.0.0", "foo"]) == "v1.0.0"
