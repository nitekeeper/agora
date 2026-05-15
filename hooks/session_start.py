# hooks/session_start.py
"""Claude Code SessionStart hook for the agora plugin.

Responsibilities:
  1. Staleness check: recompile .claude-plugin/marketplace.json if it is
     missing or older than plugins.json.
  2. (Future) Update banner: print pending plugin updates from the local
     check cache. Implemented by task 32.

This hook MUST NEVER block session start. Any exception during a check is
swallowed (with a one-line stderr warning) so Claude Code's session still
proceeds.
"""
from __future__ import annotations

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
    except Exception as e:  # noqa: BLE001 - hook must never raise
        print(f"agora session-start hook: {e}", file=sys.stderr)


# TODO(task 32): show_update_banner() call goes here.


def main() -> int:
    check_staleness()
    # show_update_banner()    # added by task 32
    return 0


if __name__ == "__main__":
    sys.exit(main())
