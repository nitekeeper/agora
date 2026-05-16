# hooks/session_start.py
"""Claude Code SessionStart hook for the agora plugin.

Responsibilities:
  1. Staleness check: recompile .claude-plugin/marketplace.json if it is
     missing or older than plugins.json.
  2. Opportunistic refresh: if the check cache is older than the
     opportunistic-refresh threshold (1 hour), kick off a detached
     `agora:check` subprocess so the cache stays fresh without the user
     having to remember to run it.
  3. Update banner: print pending plugin updates from the local check cache.

This hook MUST NEVER block session start. Any exception during a check is
swallowed (with a one-line stderr warning) so Claude Code's session still
proceeds. The opportunistic refresh is spawned detached so even a slow
network call cannot delay session start.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Support invocation from any cwd. Claude Code may call this script directly.
_HOOKS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HOOKS_DIR.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import compile, paths  # noqa: E402

# How stale the cache has to be before we kick off a background refresh.
# Shorter than check.py's own 24h TTL: we want freshness, but not so often
# that every session start spawns a network call. 1h is a reasonable middle
# ground for "feels live without spamming the network."
_OPPORTUNISTIC_TTL = timedelta(hours=1)


def _cache_age() -> timedelta | None:
    """Return the cache's age, or None if the cache is missing or unreadable."""
    cache_path = paths.CHECK_CACHE_JSON
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    fetched_at = data.get("fetched_at") if isinstance(data, dict) else None
    if not isinstance(fetched_at, str) or not fetched_at:
        return None
    try:
        s = fetched_at[:-1] + "+00:00" if fetched_at.endswith("Z") else fetched_at
        stamp = datetime.fromisoformat(s)
    except ValueError:
        return None
    return datetime.now(timezone.utc) - stamp


def _spawn_detached_check() -> None:
    """Run `agora:check` as a fully-detached background subprocess.

    Returns immediately. On Windows, suppresses the console window flash via
    CREATE_NO_WINDOW + DETACHED_PROCESS flags. On POSIX, starts a new session
    so the child survives the hook's exit.
    """
    cmd = [sys.executable, "-m", "scripts.check"]
    kwargs: dict = {
        "cwd": str(_REPO_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # DETACHED_PROCESS (0x00000008) — fully detach from parent console.
        # CREATE_NO_WINDOW (0x08000000) — no terminal flash.
        kwargs["creationflags"] = 0x00000008 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    # Static command list, no shell — safe to spawn as Popen.
    subprocess.Popen(cmd, **kwargs)


def opportunistic_refresh() -> None:
    """If the cache is missing or older than _OPPORTUNISTIC_TTL, spawn a
    detached `agora:check` so the cache is fresh by the user's next session.

    The refresh runs in the background; this function returns immediately.
    The banner this session shows still reflects the pre-refresh cache —
    that's fine, the user sees fresh data next session.
    """
    try:
        age = _cache_age()
        if age is not None and age < _OPPORTUNISTIC_TTL:
            return  # cache is fresh enough; skip
        _spawn_detached_check()
    except Exception as e:
        print(f"agora opportunistic refresh: {e}", file=sys.stderr)


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
    opportunistic_refresh()
    show_update_banner()
    return 0


if __name__ == "__main__":
    sys.exit(main())
