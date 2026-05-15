"""Validate docs/plugins.schema.json against good and bad fixtures."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "plugins.schema.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    # Will raise SchemaError if the schema itself is invalid.
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture
def good_doc() -> dict:
    return {
        "$schema": "https://nitekeeper.github.io/agora/plugins.schema.json",
        "marketplace": {
            "name": "agora",
            "description": "Custom Claude Code plugin marketplace",
            "owner": {"name": "nitekeeper"},
        },
        "plugins": [
            {
                "name": "nitekeeper-atelier",
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
        ],
    }


def test_schema_is_valid_draft_2020_12(schema: dict) -> None:
    Draft202012Validator.check_schema(schema)


def test_good_doc_validates(validator: Draft202012Validator, good_doc: dict) -> None:
    errors = list(validator.iter_errors(good_doc))
    assert errors == [], f"Expected no errors, got: {[e.message for e in errors]}"


def test_missing_required_name(validator: Draft202012Validator, good_doc: dict) -> None:
    doc = copy.deepcopy(good_doc)
    del doc["plugins"][0]["name"]
    assert not validator.is_valid(doc)


def test_invalid_semver(validator: Draft202012Validator, good_doc: dict) -> None:
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["current_version"] = "1.x.0"
    assert not validator.is_valid(doc)


def test_wrong_sha_length(validator: Draft202012Validator, good_doc: dict) -> None:
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["current_sha"] = "abc123"
    assert not validator.is_valid(doc)


def test_non_https_repository_url(validator: Draft202012Validator, good_doc: dict) -> None:
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["repository_url"] = "http://github.com/x/y.git"
    assert not validator.is_valid(doc)


def test_license_not_in_enum(validator: Draft202012Validator, good_doc: dict) -> None:
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["license"] = "WTFPL"
    assert not validator.is_valid(doc)


def test_additional_properties_rejected(validator: Draft202012Validator, good_doc: dict) -> None:
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["repository_ur"] = "https://github.com/x/y.git"
    assert not validator.is_valid(doc)


def test_name_pattern_uppercase_rejected(validator: Draft202012Validator, good_doc: dict) -> None:
    doc = copy.deepcopy(good_doc)
    doc["plugins"][0]["name"] = "Nitekeeper-Atelier"
    assert not validator.is_valid(doc)
