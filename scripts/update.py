# scripts/update.py
"""agora:update — refresh the pinned version + SHA of one or all registered
plugins by checking their git tags.

For each target plugin, runs `git ls-remote --tags <repository_url>`, picks
the latest stable (or prerelease, with --include-prerelease) tag, compares
to the entry's current_version, and writes back current_version, current_sha,
and updated_at when a newer version is available.

Errors for a single plugin (network failure, no eligible tags) are logged
to stderr and the batch continues. plugins.json + marketplace.json are
written atomically as a pair via registry.save_registry().
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Support both `python3 -m scripts.update` and `python3 scripts/update.py`
# invocations by ensuring the repo root is on sys.path for the direct case.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import git_helpers, registry, semver
from scripts.git_helpers import GitError


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_workflow_hint(names: list[str]) -> str:
    joined = " ".join(names)
    return f'git add plugins.json; git commit -m "Update {joined}"; git push; gh pr create'


def _select_targets(data: dict, name: str | None, all_flag: bool) -> list[dict] | int:
    """Return the list of plugin entries to process, or an exit code on error."""
    if name:
        found = registry.find_plugin(data, name)
        if found is None:
            print(f"plugin not found: {name}", file=sys.stderr)
            return 1
        _, entry = found
        return [entry]
    if all_flag:
        return list(data.get("plugins", []))
    print(
        "usage: agora:update <name> | --all  (one of these is required)",
        file=sys.stderr,
    )
    return 1


def _process_plugin(entry: dict, include_prerelease: bool) -> tuple[str, str | None, str | None]:
    """Return (status, old_version, new_version).

    status is one of: "updated", "up-to-date", "error".
    """
    name = entry.get("name", "<unknown>")
    url = entry.get("repository_url", "")
    current = entry.get("current_version", "")

    try:
        tags = git_helpers.ls_remote_tags(url)
    except GitError as e:
        print(f"{name}: {e}", file=sys.stderr)
        return "error", current, None

    if not tags:
        print(f"{name}: no eligible tags", file=sys.stderr)
        return "error", current, None

    latest = semver.pick_latest(list(tags.keys()), include_prerelease=include_prerelease)
    if latest is None:
        print(f"{name}: no eligible tags", file=sys.stderr)
        return "error", current, None

    current_ver = semver.parse(current)
    latest_ver = semver.parse(latest)
    if latest_ver is None:
        print(f"{name}: no eligible tags", file=sys.stderr)
        return "error", current, None

    if current_ver is None or current_ver < latest_ver:
        entry["current_version"] = latest
        entry["current_sha"] = tags[latest]
        entry["updated_at"] = _now_iso()
        return "updated", current, latest
    return "up-to-date", current, latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agora:update",
        description=(
            "Refresh the pinned version + SHA of one or all registered "
            "plugins by checking git tags."
        ),
    )
    parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Plugin name to update. Omit and pass --all for a full refresh.",
    )
    parser.add_argument(
        "--all",
        dest="all_flag",
        action="store_true",
        help="Update every plugin in the registry.",
    )
    parser.add_argument(
        "--include-prerelease",
        dest="include_prerelease",
        action="store_true",
        help="Allow prerelease tags (e.g. v1.0.0-rc.1) when selecting the latest.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print the changes that would be made without writing.",
    )
    args = parser.parse_args(argv)

    if args.name and args.all_flag:
        print(
            "usage: pass either <name> or --all, not both",
            file=sys.stderr,
        )
        return 1

    data = registry.load_registry()
    targets = _select_targets(data, args.name, args.all_flag)
    if isinstance(targets, int):
        return targets

    updated_names: list[str] = []
    for entry in targets:
        name = entry.get("name", "<unknown>")
        status, old_version, new_version = _process_plugin(entry, args.include_prerelease)
        if status == "updated":
            print(f"{name}: {old_version} -> {new_version}")
            updated_names.append(name)
        elif status == "up-to-date":
            print(f"{name}: up to date ({old_version})")
        else:
            # Error already logged to stderr; surface a short stdout line too.
            print(f"{name}: error (no tags)")

    if updated_names and not args.dry_run:
        registry.save_registry(data)

    if args.dry_run and updated_names:
        print(f"Dry run - {len(updated_names)} plugin(s) would be updated.")
    elif updated_names:
        print(f"Updated {len(updated_names)} plugin(s).")
        print(_git_workflow_hint(updated_names))
    else:
        print("No updates available.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
