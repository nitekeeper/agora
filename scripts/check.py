# scripts/check.py
"""agora:check — refresh the local "latest available version" cache.

Iterates `plugins.json`, runs `git ls-remote --tags` against each repository,
picks the highest semver tag per plugin, and writes the result to
`~/.agora/check-cache.json`. The session-start update banner reads that cache
to surface available upgrades without going to the network on every prompt.

Honors a 24-hour TTL by default; pass `--force` to refresh anyway. Use
`--include-prerelease` to consider prerelease tags. `--json` swaps the human
progress output for the full cache dict on stdout (cache file is still
written).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Support both `python -m scripts.check` and `python scripts/check.py`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import git_helpers, paths, semver
from scripts.atomic import atomic_write
from scripts.registry import load_registry

_TTL = timedelta(hours=24)


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_z(stamp: str) -> datetime | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        # Accept both "...Z" and "...+00:00" suffixes.
        s = stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _load_cache(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _cache_is_fresh(cache: dict[str, Any]) -> tuple[bool, float | None]:
    """Return (is_fresh, age_in_hours)."""
    fetched_at = _parse_iso_z(cache.get("fetched_at", ""))
    if fetched_at is None:
        return False, None
    age = datetime.now(timezone.utc) - fetched_at
    hours = age.total_seconds() / 3600.0
    return age < _TTL, hours


def _check_one(
    plugin: dict[str, Any],
    include_prerelease: bool,
) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    url = plugin.get("repository_url", "")
    try:
        tags = git_helpers.ls_remote_tags(url)
    except git_helpers.GitError as e:
        entry["latest_version"] = None
        entry["error"] = str(e)
        entry["checked_at"] = _now_iso_z()
        return entry
    latest = semver.pick_latest(
        list(tags.keys()), include_prerelease=include_prerelease
    )
    entry["latest_version"] = latest
    entry["checked_at"] = _now_iso_z()
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agora:check",
        description=(
            "Refresh the local 'latest available version' cache for every "
            "registered plugin."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the 24h TTL and refresh anyway.",
    )
    parser.add_argument(
        "--include-prerelease",
        dest="include_prerelease",
        action="store_true",
        help="Allow prereleases in the latest pick.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit the full cache dict as JSON to stdout (cache file still written).",
    )
    args = parser.parse_args(argv)

    registry = load_registry(paths.PLUGINS_JSON)
    plugins = registry.get("plugins", []) or []

    # Empty registry — write empty cache and exit.
    if not plugins:
        cache: dict[str, Any] = {
            "fetched_at": _now_iso_z(),
            "include_prerelease": args.include_prerelease,
            "plugins": {},
        }
        paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write(paths.CHECK_CACHE_JSON, json.dumps(cache, indent=2) + "\n")
        if args.as_json:
            sys.stdout.write(json.dumps(cache, indent=2))
            sys.stdout.write("\n")
        else:
            print("Checked 0 plugin(s) — 0 outdated, 0 errors.")
        return 0

    # TTL check.
    if not args.force:
        existing = _load_cache(paths.CHECK_CACHE_JSON)
        if existing is not None:
            fresh, hours = _cache_is_fresh(existing)
            if fresh and hours is not None:
                msg = (
                    f"cache is fresh (refreshed {hours:.1f} hours ago); "
                    "use --force to refresh anyway"
                )
                if args.as_json:
                    sys.stdout.write(json.dumps(existing, indent=2))
                    sys.stdout.write("\n")
                else:
                    print(msg)
                return 0

    # Per-plugin checks.
    per_plugin: dict[str, dict[str, Any]] = {}
    outdated = 0
    errors = 0
    for p in plugins:
        name = p.get("name", "")
        if not name:
            continue
        entry = _check_one(p, args.include_prerelease)
        per_plugin[name] = entry

        latest = entry.get("latest_version")
        current = p.get("current_version")
        err = entry.get("error")
        if err:
            errors += 1
            if not args.as_json:
                # Strip excess detail from error messages for the progress line.
                short = err.split(":", 1)[0]
                print(f"  {name}: ERROR ({short})")
        else:
            if latest is not None and latest != current:
                outdated += 1
            if not args.as_json:
                shown = latest if latest else "(no eligible tags)"
                print(f"  {name}: {shown}")

    cache = {
        "fetched_at": _now_iso_z(),
        "include_prerelease": args.include_prerelease,
        "plugins": per_plugin,
    }

    paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(paths.CHECK_CACHE_JSON, json.dumps(cache, indent=2) + "\n")

    if args.as_json:
        sys.stdout.write(json.dumps(cache, indent=2))
        sys.stdout.write("\n")
    else:
        print(
            f"Checked {len(per_plugin)} plugin(s) — "
            f"{outdated} outdated, {errors} errors."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
