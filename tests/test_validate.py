"""Tests for scripts/validate.py."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from scripts import validate as validate_mod
from scripts.paths import SCHEMA_JSON
from scripts.validate import main, validate

# ---------- fixtures ----------


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture
def good_plugin() -> dict:
    return {
        "name": "atelier",
        "repository_url": "https://github.com/nitekeeper/atelier.git",
        "current_version": "v1.0.0",
        "current_sha": "abc1230000000000000000000000000000000000",
        "description": "Shared workspace methodology and dev workflow for human-AI development teams",
        "license": "MIT",
        "category": "development",
        "keywords": ["workflow", "tdd", "skills"],
        "author": {"name": "nitekeeper"},
        "homepage": "https://github.com/nitekeeper/atelier",
        "registered_at": "2026-05-15T19:00:00Z",
        "updated_at": "2026-05-15T19:00:00Z",
    }


@pytest.fixture
def good_doc(good_plugin) -> dict:
    return {
        "$schema": "https://nitekeeper.github.io/agora/plugins.schema.json",
        "marketplace": {
            "name": "agora",
            "description": "Custom Claude Code plugin marketplace",
            "owner": {"name": "nitekeeper"},
        },
        "plugins": [good_plugin],
    }


@pytest.fixture
def empty_doc() -> dict:
    return {
        "$schema": "https://nitekeeper.github.io/agora/plugins.schema.json",
        "marketplace": {
            "name": "agora",
            "description": "Custom Claude Code plugin marketplace",
            "owner": {"name": "nitekeeper"},
        },
        "plugins": [],
    }


@pytest.fixture
def write_doc(tmp_path):
    """Returns a function (doc) -> path that writes doc to tmp plugins.json."""

    def _w(doc: dict) -> Path:
        p = tmp_path / "plugins.json"
        _write_json(p, doc)
        return p

    return _w


# ---------- structural happy paths ----------


def test_valid_empty_plugins(write_doc, empty_doc):
    errors = validate(plugins_path=write_doc(empty_doc), schema_path=SCHEMA_JSON)
    assert errors == []


def test_valid_full_plugin(write_doc, good_doc):
    errors = validate(plugins_path=write_doc(good_doc), schema_path=SCHEMA_JSON)
    assert errors == [], [e.message for e in errors]


# ---------- structural violations ----------


def test_missing_required_field(write_doc, good_doc):
    doc = copy.deepcopy(good_doc)
    del doc["plugins"][0]["current_sha"]
    errors = validate(plugins_path=write_doc(doc), schema_path=SCHEMA_JSON)
    assert len(errors) == 1
    assert "/plugins/0" in errors[0].location
    assert "current_sha" in errors[0].message


def test_invalid_semver_pattern(write_doc, good_doc):
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["current_version"] = "1.x.0"
    errors = validate(plugins_path=write_doc(doc), schema_path=SCHEMA_JSON)
    assert len(errors) == 1
    assert "/plugins/0/current_version" in errors[0].location


def test_additional_properties_typo(write_doc, good_doc):
    doc = copy.deepcopy(good_doc)
    # Note: schema requires repository_url, so add the typo without removing.
    doc["plugins"][0]["repository_ur"] = "https://github.com/x/y.git"
    errors = validate(plugins_path=write_doc(doc), schema_path=SCHEMA_JSON)
    assert len(errors) == 1
    msg = errors[0].message.lower()
    assert "additional" in msg or "not allowed" in msg or "unevaluated" in msg


def test_license_not_in_enum(write_doc, good_doc):
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["license"] = "WTFPL"
    errors = validate(plugins_path=write_doc(doc), schema_path=SCHEMA_JSON)
    assert len(errors) == 1
    assert "/plugins/0/license" in errors[0].location


# ---------- uniqueness ----------


def test_duplicate_name(write_doc, good_doc, good_plugin):
    doc = copy.deepcopy(good_doc)
    dup = copy.deepcopy(good_plugin)
    # Same name, different repository_url so the dup-url check doesn't also fire.
    dup["repository_url"] = "https://github.com/nitekeeper/other.git"
    doc["plugins"].append(dup)
    errors = validate(plugins_path=write_doc(doc), schema_path=SCHEMA_JSON)
    name_dups = [e for e in errors if "uniqueness" in e.location and "name" in e.message]
    assert len(name_dups) == 1
    assert "atelier" in name_dups[0].message


def test_duplicate_repository_url(write_doc, good_doc, good_plugin):
    doc = copy.deepcopy(good_doc)
    dup = copy.deepcopy(good_plugin)
    dup["name"] = "other"
    doc["plugins"].append(dup)
    errors = validate(plugins_path=write_doc(doc), schema_path=SCHEMA_JSON)
    url_dups = [e for e in errors if "uniqueness" in e.location and "repository_url" in e.message]
    assert len(url_dups) == 1


# ---------- multiple errors aggregated ----------


def test_multiple_errors(write_doc, good_doc):
    doc = copy.deepcopy(good_doc)
    # 1) bad semver
    doc["plugins"][0]["current_version"] = "1.x.0"
    # 2) bad sha
    doc["plugins"][0]["current_sha"] = "abc123"
    # 3) bad license
    doc["plugins"][0]["license"] = "WTFPL"
    errors = validate(plugins_path=write_doc(doc), schema_path=SCHEMA_JSON)
    assert len(errors) == 3
    locs = {e.location for e in errors}
    assert any("current_version" in l for l in locs)
    assert any("current_sha" in l for l in locs)
    assert any("license" in l for l in locs)


# ---------- file errors ----------


def test_missing_plugins_json(tmp_path):
    missing = tmp_path / "nope.json"
    errors = validate(plugins_path=missing, schema_path=SCHEMA_JSON)
    assert len(errors) == 1
    assert "not found" in errors[0].message.lower()


def test_malformed_plugins_json(tmp_path):
    p = tmp_path / "plugins.json"
    p.write_text("{not valid json", encoding="utf-8")
    errors = validate(plugins_path=p, schema_path=SCHEMA_JSON)
    assert len(errors) == 1
    assert "invalid json" in errors[0].message.lower()


def test_missing_schema_file_raises(tmp_path, write_doc, empty_doc):
    plugins_path = write_doc(empty_doc)
    missing_schema = tmp_path / "no-schema.json"
    with pytest.raises(FileNotFoundError):
        validate(plugins_path=plugins_path, schema_path=missing_schema)


# ---------- connectivity (mocked) ----------


def _mk_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["git", "ls-remote"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_connectivity_ok(write_doc, good_doc, good_plugin):
    sha = good_plugin["current_sha"]
    ver = good_plugin["current_version"]
    stdout = f"{sha}\trefs/tags/{ver}\n"
    with mock.patch.object(
        validate_mod.subprocess, "run", return_value=_mk_completed(stdout=stdout)
    ) as m:
        errors = validate(
            plugins_path=write_doc(good_doc),
            schema_path=SCHEMA_JSON,
            connectivity=True,
        )
    assert errors == [], [e.message for e in errors]
    assert m.called


def test_connectivity_tag_missing(write_doc, good_doc, good_plugin):
    # ls-remote returns a different tag.
    other_sha = "f" * 40
    stdout = f"{other_sha}\trefs/tags/v9.9.9\n"
    with mock.patch.object(
        validate_mod.subprocess, "run", return_value=_mk_completed(stdout=stdout)
    ):
        errors = validate(
            plugins_path=write_doc(good_doc),
            schema_path=SCHEMA_JSON,
            connectivity=True,
        )
    conn = [e for e in errors if "current_version" in e.location]
    assert len(conn) == 1
    assert good_plugin["name"] in conn[0].location
    assert "not found" in conn[0].message.lower()


def test_connectivity_sha_mismatch(write_doc, good_doc, good_plugin):
    ver = good_plugin["current_version"]
    wrong_sha = "f" * 40
    stdout = f"{wrong_sha}\trefs/tags/{ver}\n"
    with mock.patch.object(
        validate_mod.subprocess, "run", return_value=_mk_completed(stdout=stdout)
    ):
        errors = validate(
            plugins_path=write_doc(good_doc),
            schema_path=SCHEMA_JSON,
            connectivity=True,
        )
    conn = [e for e in errors if "current_sha" in e.location]
    assert len(conn) == 1
    assert "mismatch" in conn[0].message.lower()


def test_connectivity_timeout(write_doc, good_doc):
    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0] if a else "git", timeout=10)

    with mock.patch.object(validate_mod.subprocess, "run", side_effect=_raise):
        errors = validate(
            plugins_path=write_doc(good_doc),
            schema_path=SCHEMA_JSON,
            connectivity=True,
        )
    assert len(errors) == 1
    assert "timed out" in errors[0].message.lower()


def test_connectivity_git_not_installed(write_doc, good_doc):
    def _raise(*a, **kw):
        raise FileNotFoundError("git not installed")

    with mock.patch.object(validate_mod.subprocess, "run", side_effect=_raise):
        errors = validate(
            plugins_path=write_doc(good_doc),
            schema_path=SCHEMA_JSON,
            connectivity=True,
        )
    assert len(errors) == 1
    assert "git executable not found" in errors[0].message.lower()


def test_connectivity_annotated_tag_peeled(write_doc, good_doc, good_plugin):
    """Annotated tag: direct ref points at tag object, ^{} points at commit."""
    ver = good_plugin["current_version"]
    pinned_sha = good_plugin["current_sha"]
    tag_obj_sha = "9" * 40
    stdout = f"{tag_obj_sha}\trefs/tags/{ver}\n{pinned_sha}\trefs/tags/{ver}^{{}}\n"
    with mock.patch.object(
        validate_mod.subprocess, "run", return_value=_mk_completed(stdout=stdout)
    ):
        errors = validate(
            plugins_path=write_doc(good_doc),
            schema_path=SCHEMA_JSON,
            connectivity=True,
        )
    assert errors == [], [e.message for e in errors]


# ---------- CLI ----------


def test_cli_exit_zero_on_valid(write_doc, empty_doc, capsys):
    rc = main(["--plugins", str(write_doc(empty_doc)), "--schema", str(SCHEMA_JSON)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "plugins.json is valid" in captured.out


def test_cli_exit_one_on_invalid(write_doc, good_doc, capsys):
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["license"] = "WTFPL"
    rc = main(["--plugins", str(write_doc(doc)), "--schema", str(SCHEMA_JSON)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "[error]" in captured.out


def test_cli_json_output_valid(write_doc, empty_doc, capsys):
    rc = main(
        [
            "--plugins",
            str(write_doc(empty_doc)),
            "--schema",
            str(SCHEMA_JSON),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload == {"errors": []}


def test_cli_json_output_invalid(write_doc, good_doc, capsys):
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["license"] = "WTFPL"
    rc = main(
        [
            "--plugins",
            str(write_doc(doc)),
            "--schema",
            str(SCHEMA_JSON),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    payload = json.loads(captured.out)
    assert "errors" in payload
    assert len(payload["errors"]) == 1
    err = payload["errors"][0]
    assert err["severity"] == "error"
    assert "license" in err["location"]
