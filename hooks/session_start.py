# hooks/session_start.py
"""Claude Code SessionStart hook for the agora plugin.

Responsibilities:
  1. Staleness check: recompile .claude-plugin/marketplace.json if it is
     missing or older than plugins.json.
  2. Update banner: print pending plugin updates from the local check cache.

This hook MUST NEVER block session start. Any exception during a check is
swallowed (with a one-line stderr warning) so Claude Code's session still
proceeds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Support invocation from any cwd. Claude Code may call this script directly.
_HOOKS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HOOKS_DIR.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import compile, paths  # noqa: E402


def check_staleness() -> None:
    """Recompile marketplace.json if it is missing or older than plugins.json."""
    try:
        plugins_path = paths.PLUGINS_JSON
        marketplace_path = paths.MARKETPLACE_JSON

        if not plugins_path.exists():
            # Misconfigured repo; not our problem.
            return

        if not marketplace_path.exists():
            compile.compile_to_disk()
            return

        plugins_mtime = plugins_path.stat().st_mtime
        marketplace_mtime = marketplace_path.stat().st_mtime
        if plugins_mtime > marketplace_mtime:
            compile.compile_to_disk()
    except Exception as e:
        print(f"agora session-start hook: {e}", file=sys.stderr)


def show_update_banner() -> None:
    """Print a banner listing plugins with newer versions available in the cache."""
    try:
        cache_path = paths.CHECK_CACHE_JSON
        plugins_path = paths.PLUGINS_JSON

        if not cache_path.exists() or not plugins_path.exists():
            return

        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        try:
            plugins_doc = json.loads(plugins_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        cache_plugins = cache.get("plugins") or {}
        updates: list[tuple[str, str, str]] = []
        for plugin in plugins_doc.get("plugins") or []:
            name = plugin.get("name")
            current = plugin.get("current_version")
            if not name:
                continue
            entry = cache_plugins.get(name)
            if not entry:
                continue
            latest = entry.get("latest_version")
            if not latest:
                continue
            if latest != current:
                updates.append((name, current, latest))

        if not updates:
            return

        name_width = max(len(name) for name, _, _ in updates)
        print("Plugin updates available:")
        for name, current, latest in updates:
            print(f"  {name.ljust(name_width)}  {current} -> {latest}")
        print()
        print("Run `agora:update --all` to upgrade, or `agora:check` to refresh the cache.")
    except Exception as e:
        print(f"agora session-start banner: {e}", file=sys.stderr)


def main() -> int:
    check_staleness()
    show_update_banner()
    return 0


if __name__ == "__main__":
    sys.exit(main())
