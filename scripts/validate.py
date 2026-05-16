# scripts/validate.py
"""Read-only structural and connectivity validation for plugins.json.

Two layers:

1. Structural — JSON Schema (Draft 2020-12) validation plus per-script
   uniqueness checks the schema cannot express (plugin name, repository_url).
2. Connectivity (opt-in via --connectivity) — `git ls-remote --tags <url>`
   per plugin, verifying each `current_version` tag exists and resolves to
   `current_sha`.

CLI exit codes: 0 = valid, 1 = invalid. `--json` controls output format only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Support both `python -m scripts.validate` and `python scripts/validate.py`
# invocations by ensuring the repo root is on sys.path for the direct case.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jsonschema import Draft202012Validator

from scripts.paths import PLUGINS_JSON, SCHEMA_JSON

_LS_REMOTE_TIMEOUT_SEC = 10


@dataclass
class ValidationError:
    severity: str  # 'error' or 'warning'
    location: str  # JSON pointer or descriptive path
    message: str


def _json_pointer(path) -> str:
    """Convert a jsonschema error.absolute_path deque into a JSON pointer."""
    parts = []
    for p in path:
        # Escape per RFC 6901
        s = str(p).replace("~", "~0").replace("/", "~1")
        parts.append(s)
    return "/" + "/".join(parts) if parts else ""


def _load_json(path: Path) -> tuple[object | None, ValidationError | None]:
    if not path.exists():
        return None, ValidationError(
            severity="error",
            location=str(path),
            message=f"file not found: {path}",
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return None, ValidationError(
            severity="error",
            location=str(path),
            message=f"could not read file: {e}",
        )
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, ValidationError(
            severity="error",
            location=str(path),
            message=f"invalid JSON: {e.msg} (line {e.lineno}, col {e.colno})",
        )


def _structural_errors(instance: object, schema: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    validator = Draft202012Validator(schema)
    for err in validator.iter_errors(instance):
        errors.append(
            ValidationError(
                severity="error",
                location=_json_pointer(err.absolute_path) or "/",
                message=err.message,
            )
        )
    return errors


def _uniqueness_errors(instance: object) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(instance, dict):
        return errors
    plugins = instance.get("plugins")
    if not isinstance(plugins, list):
        return errors

    seen_names: dict[str, int] = {}
    seen_urls: dict[str, int] = {}
    for idx, plugin in enumerate(plugins):
        if not isinstance(plugin, dict):
            continue
        name = plugin.get("name")
        url = plugin.get("repository_url")
        if isinstance(name, str):
            if name in seen_names:
                errors.append(
                    ValidationError(
                        severity="error",
                        location="/plugins (uniqueness)",
                        message=(
                            f"duplicate plugin name '{name}' at index {idx} "
                            f"(first seen at index {seen_names[name]})"
                        ),
                    )
                )
            else:
                seen_names[name] = idx
        if isinstance(url, str):
            if url in seen_urls:
                errors.append(
                    ValidationError(
                        severity="error",
                        location="/plugins (uniqueness)",
                        message=(
                            f"duplicate repository_url '{url}' at index {idx} "
                            f"(first seen at index {seen_urls[url]})"
                        ),
                    )
                )
            else:
                seen_urls[url] = idx
    return errors


def _parse_ls_remote(output: str) -> dict[str, str]:
    """Parse `git ls-remote --tags <url>` output into {tag: sha}.

    Output lines look like:
        <sha>\trefs/tags/<tag>
        <sha>\trefs/tags/<tag>^{}   (peeled tag — preferred for annotated tags)

    For annotated tags, the peeled (^{}) entry points at the commit; we
    prefer that when present.
    """
    direct: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        sha, ref = line.split("\t", 1)
        if not ref.startswith("refs/tags/"):
            continue
        tag = ref[len("refs/tags/") :]
        if tag.endswith("^{}"):
            peeled[tag[:-3]] = sha
        else:
            direct[tag] = sha
    # Peeled takes precedence (points to underlying commit for annotated tags).
    merged = dict(direct)
    merged.update(peeled)
    return merged


def _connectivity_errors(instance: object) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(instance, dict):
        return errors
    plugins = instance.get("plugins")
    if not isinstance(plugins, list):
        return errors

    for idx, plugin in enumerate(plugins):
        if not isinstance(plugin, dict):
            continue
        name = plugin.get("name", f"<index {idx}>")
        url = plugin.get("repository_url")
        version = plugin.get("current_version")
        sha = plugin.get("current_sha")
        loc_prefix = f"/plugins/{idx} ({name})"

        if not isinstance(url, str) or not isinstance(version, str) or not isinstance(sha, str):
            # Structural validation should have already flagged this; skip
            # the network call.
            continue

        try:
            result = subprocess.run(
                ["git", "ls-remote", "--tags", url],
                capture_output=True,
                text=True,
                timeout=_LS_REMOTE_TIMEOUT_SEC,
                check=False,
            )
        except subprocess.TimeoutExpired:
            errors.append(
                ValidationError(
                    severity="error",
                    location=f"{loc_prefix}/repository_url",
                    message=f"git ls-remote timed out after {_LS_REMOTE_TIMEOUT_SEC}s",
                )
            )
            continue
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    severity="error",
                    location=f"{loc_prefix}/repository_url",
                    message="git executable not found on PATH",
                )
            )
            continue
        except OSError as e:
            errors.append(
                ValidationError(
                    severity="error",
                    location=f"{loc_prefix}/repository_url",
                    message=f"git ls-remote failed: {e}",
                )
            )
            continue

        if result.returncode != 0:
            stderr = (result.stderr or "").strip().splitlines()
            detail = stderr[-1] if stderr else f"exit {result.returncode}"
            errors.append(
                ValidationError(
                    severity="error",
                    location=f"{loc_prefix}/repository_url",
                    message=f"git ls-remote failed: {detail}",
                )
            )
            continue

        tags = _parse_ls_remote(result.stdout)
        if version not in tags:
            errors.append(
                ValidationError(
                    severity="error",
                    location=f"{loc_prefix}/current_version",
                    message=f"tag '{version}' not found on remote {url}",
                )
            )
            continue

        remote_sha = tags[version]
        if remote_sha.lower() != sha.lower():
            errors.append(
                ValidationError(
                    severity="error",
                    location=f"{loc_prefix}/current_sha",
                    message=(
                        f"current_sha mismatch: plugins.json has '{sha}', "
                        f"remote tag '{version}' resolves to '{remote_sha}'"
                    ),
                )
            )

    return errors


def validate(
    plugins_path: Path = PLUGINS_JSON,
    schema_path: Path = SCHEMA_JSON,
    connectivity: bool = False,
) -> list[ValidationError]:
    """Validate plugins.json. Returns a list of errors; empty means valid.

    Does not raise on validation failures. Raises FileNotFoundError if the
    schema file is missing (programming/install error, not a validation error).
    """
    if not schema_path.exists():
        raise FileNotFoundError(f"schema file not found: {schema_path}")

    schema_data, schema_err = _load_json(schema_path)
    if schema_err is not None:
        # Schema malformed — treat as a programming error.
        raise ValueError(f"schema is not valid JSON: {schema_err.message}")

    instance, load_err = _load_json(plugins_path)
    if load_err is not None:
        return [load_err]

    errors = _structural_errors(instance, schema_data)  # type: ignore[arg-type]
    errors.extend(_uniqueness_errors(instance))
    if connectivity:
        errors.extend(_connectivity_errors(instance))
    return errors


def _print_human(errors: list[ValidationError], connectivity: bool) -> None:
    if not errors:
        print("plugins.json is valid")
        if connectivity:
            print("connectivity check passed")
        return
    for err in errors:
        print(f"[{err.severity}] {err.location}: {err.message}")


def _print_json(errors: list[ValidationError]) -> None:
    payload = {"errors": [asdict(e) for e in errors]}
    print(json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate plugins.json against the JSON schema.")
    parser.add_argument(
        "--connectivity",
        action="store_true",
        help="Also verify each plugin's git URL/tag/SHA resolves remotely.",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    parser.add_argument(
        "--plugins",
        type=Path,
        default=PLUGINS_JSON,
        help="Path to plugins.json (default: repo root).",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_JSON,
        help="Path to plugins.schema.json (default: docs/).",
    )
    args = parser.parse_args(argv)

    try:
        errors = validate(
            plugins_path=args.plugins,
            schema_path=args.schema,
            connectivity=args.connectivity,
        )
    except (FileNotFoundError, ValueError) as e:
        # Programming/install error — surface and exit nonzero.
        if args.json_out:
            print(
                json.dumps(
                    {
                        "errors": [
                            {
                                "severity": "error",
                                "location": "<setup>",
                                "message": str(e),
                            }
                        ]
                    },
                    indent=2,
                )
            )
        else:
            print(f"[error] <setup>: {e}", file=sys.stderr)
        return 1

    if args.json_out:
        _print_json(errors)
    else:
        _print_human(errors, connectivity=args.connectivity)

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
