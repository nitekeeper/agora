# scripts/list_plugins.py
"""agora:list — print a summary of registered plugins from plugins.json.

Mirrors `brew list` / `apt list` / `npm list` style: a pipe-friendly columnar
table by default, with --check for outdated-status and --json for machine
consumption.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Support both `python -m scripts.list_plugins` and `python scripts/list_plugins.py`
# invocations by ensuring the repo root is on sys.path for the direct case.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import paths

ANSI_BOLD = "\x1b[1m"
ANSI_RESET = "\x1b[0m"

# Sensible minimums so the header line aligns even with very narrow data.
_DEFAULT_MIN_WIDTHS = {
    "NAME": 4,
    "VERSION": 7,
    "CURRENT": 7,
    "LATEST": 6,
    "LICENSE": 7,
    "CATEGORY": 8,
    "STATUS": 10,
}


def _load_plugins(plugins_path: Path) -> list[dict[str, Any]]:
    """Load plugins.json. Exits with code 1 on missing or malformed file."""
    if not plugins_path.exists():
        print(
            f"agora:list error — plugins.json not found at {plugins_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        data = json.loads(plugins_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(
            f"agora:list error — plugins.json is malformed: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        print(
            "agora:list error — plugins.json 'plugins' field is not a list",
            file=sys.stderr,
        )
        sys.exit(1)
    return plugins


def _load_cache(cache_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load the check-cache. Returns (cache_plugins_dict, warning_message).

    Best-effort: missing or malformed cache returns (None, warning).
    """
    if not cache_path.exists():
        warning = (
            f"agora:check cache not found at {cache_path} — "
            "run `python scripts/check.py` to refresh"
        )
        return None, warning
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        warning = (
            f"agora:check cache at {cache_path} is malformed ({e}) — "
            "run `python scripts/check.py` to refresh"
        )
        return None, warning
    cache_plugins = data.get("plugins")
    if not isinstance(cache_plugins, dict):
        warning = (
            f"agora:check cache at {cache_path} has no 'plugins' map — "
            "run `python scripts/check.py` to refresh"
        )
        return None, warning
    return cache_plugins, None


def _status_for(current: str, cache_entry: dict[str, Any] | None) -> tuple[str, str]:
    """Return (latest_version, status) tuple."""
    if cache_entry is None:
        return ("-", "unknown")
    latest = cache_entry.get("latest_version")
    if not isinstance(latest, str) or not latest:
        return ("-", "unknown")
    if latest == current:
        return (latest, "up-to-date")
    return (latest, "outdated")


def _format_table(
    headers: list[str],
    rows: list[list[str]],
    use_color: bool,
) -> str:
    """Two-space-separated columnar output. Header bolded if use_color."""
    widths: list[int] = []
    for i, h in enumerate(headers):
        col_min = _DEFAULT_MIN_WIDTHS.get(h, len(h))
        col_width = (
            max(len(h), col_min, *(len(r[i]) for r in rows)) if rows else max(len(h), col_min)
        )
        widths.append(col_width)

    def render_row(cells: list[str]) -> str:
        # Pad every column to its width; rstrip the final composed line to drop trailing spaces.
        parts = [cells[i].ljust(widths[i]) for i in range(len(cells))]
        return "  ".join(parts).rstrip()

    header_line = render_row(headers)
    if use_color:
        header_line = f"{ANSI_BOLD}{header_line}{ANSI_RESET}"
    lines = [header_line]
    for r in rows:
        lines.append(render_row(r))
    return "\n".join(lines)


def _default_rows(plugins: list[dict[str, Any]]) -> list[list[str]]:
    rows = []
    for p in plugins:
        rows.append(
            [
                str(p.get("name", "-")),
                str(p.get("current_version", "-")),
                str(p.get("license", "-")),
                str(p.get("category", "-")),
            ]
        )
    return rows


def _check_rows(
    plugins: list[dict[str, Any]],
    cache_plugins: dict[str, Any] | None,
) -> list[list[str]]:
    rows = []
    for p in plugins:
        name = str(p.get("name", "-"))
        current = str(p.get("current_version", "-"))
        cache_entry = None
        if cache_plugins is not None:
            entry = cache_plugins.get(name)
            if isinstance(entry, dict):
                cache_entry = entry
        latest, status = _status_for(current, cache_entry)
        rows.append([name, current, latest, status])
    return rows


def _augment_json(
    plugins: list[dict[str, Any]],
    cache_plugins: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    out = []
    for p in plugins:
        entry = dict(p)
        cache_entry = None
        if cache_plugins is not None:
            ce = cache_plugins.get(p.get("name"))
            if isinstance(ce, dict):
                cache_entry = ce
        latest, status = _status_for(str(p.get("current_version", "")), cache_entry)
        entry["latest_version"] = latest if latest != "-" else None
        entry["status"] = status
        out.append(entry)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agora:list",
        description="List plugins registered in the local agora marketplace.",
    )
    parser.add_argument(
        "--check",
        "--outdated",
        dest="check",
        action="store_true",
        help="Show CURRENT / LATEST / STATUS columns using the check cache.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit JSON to stdout (pipe-friendly).",
    )
    parser.add_argument(
        "--plugins",
        dest="plugins_path",
        type=Path,
        default=paths.PLUGINS_JSON,
        help="Path to plugins.json (defaults to repo plugins.json).",
    )
    parser.add_argument(
        "--cache",
        dest="cache_path",
        type=Path,
        default=paths.CHECK_CACHE_JSON,
        help="Path to check-cache.json (defaults to ~/.agora/check-cache.json).",
    )
    args = parser.parse_args(argv)

    plugins = _load_plugins(args.plugins_path)

    cache_plugins: dict[str, Any] | None = None
    cache_warning: str | None = None
    if args.check:
        cache_plugins, cache_warning = _load_cache(args.cache_path)
        if cache_warning is not None:
            print(cache_warning, file=sys.stderr)

    # JSON mode
    if args.as_json:
        if args.check:
            payload = _augment_json(plugins, cache_plugins)
        else:
            payload = plugins
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0

    # Empty plugins
    if not plugins:
        print("(no plugins registered)")
        return 0

    # Table mode
    use_color = sys.stdout.isatty()
    if args.check:
        headers = ["NAME", "CURRENT", "LATEST", "STATUS"]
        rows = _check_rows(plugins, cache_plugins)
    else:
        headers = ["NAME", "VERSION", "LICENSE", "CATEGORY"]
        rows = _default_rows(plugins)

    print(_format_table(headers, rows, use_color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
