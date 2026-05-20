# scripts/setup.py
"""agora setup — first-time bootstrap before agora is installed as a plugin.

Registers the agora repo as a known marketplace in ~/.claude/settings.json
and runs an initial compile of marketplace.json. This is called BEFORE agora
is enabled as a Claude Code plugin; the user enables it afterward via
/plugins > Marketplaces > agora.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# Support both `python3 -m scripts.setup` and `python3 scripts/setup.py`
# invocations by ensuring the repo root is on sys.path for the direct case.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import compile as compile_module
from scripts import paths
from scripts.atomic import atomic_write


def _agora_path_string() -> str:
    """Absolute path to the agora repo, forward-slashed for JSON readability."""
    return str(paths.REPO_ROOT.resolve()).replace("\\", "/")


def _load_settings() -> dict:
    """Load ~/.claude/settings.json, returning {} if missing/empty.

    Raises SystemExit(1) on malformed JSON.
    """
    settings_path = paths.CLAUDE_SETTINGS_JSON
    if not settings_path.exists():
        return {}
    try:
        raw = settings_path.read_text(encoding="utf-8")
    except OSError as e:
        print(
            f"could not read {settings_path}: {e}",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(
            "~/.claude/settings.json is not valid JSON — fix manually before running setup",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    if not isinstance(data, dict):
        print(
            "~/.claude/settings.json is not valid JSON — fix manually before running setup",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return data


def _plan_changes(settings: dict, agora_path: str) -> tuple[dict, list[str]]:
    """Compute the new settings dict and a list of human-readable change lines.

    Returns (new_settings, diff_lines). An empty diff_lines list means no
    changes are needed.
    """
    new_settings = json.loads(json.dumps(settings))  # deep copy

    known = new_settings.get("extraKnownMarketplaces")
    if not isinstance(known, dict):
        known = {}
        new_settings["extraKnownMarketplaces"] = known
    else:
        # Re-attach in case we deep-copied — already attached, just keep ref.
        new_settings["extraKnownMarketplaces"] = known

    desired = {"source": "directory", "path": agora_path}
    existing = known.get("agora")

    diff: list[str] = []
    if existing == desired:
        return new_settings, diff

    if not isinstance(existing, dict):
        diff.append("Planned changes to ~/.claude/settings.json:")
        diff.append("")
        diff.append("  extraKnownMarketplaces.agora:")
        diff.append("    (new entry)")
        diff.append('    +   "source": "directory"')
        diff.append(f'    +   "path": "{agora_path}"')
    else:
        diff.append("Planned changes to ~/.claude/settings.json:")
        diff.append("")
        old_source = existing.get("source")
        old_path = existing.get("path")
        if old_source != "directory":
            diff.append("  extraKnownMarketplaces.agora.source:")
            diff.append(f"    -   {json.dumps(old_source)}")
            diff.append('    +   "directory"')
        if old_path != agora_path:
            diff.append("  extraKnownMarketplaces.agora.path:")
            diff.append(f'    -   "{old_path}"')
            diff.append(f'    +   "{agora_path}"')

    known["agora"] = desired
    return new_settings, diff


def _backup_settings(settings_path: Path) -> Path | None:
    """Copy settings.json to a .bak.<timestamp> sibling. Returns the backup path."""
    if not settings_path.exists():
        return None
    ts = time.strftime("%Y%m%d%H%M%S")
    backup = settings_path.with_name(settings_path.name + f".bak.{ts}")
    shutil.copy2(str(settings_path), str(backup))
    return backup


def _confirm(prompt: str) -> bool:
    try:
        response = input(prompt)
    except EOFError:
        response = ""
    return response.strip().lower() in ("y", "yes")


def run_setup(yes: bool = False) -> int:
    """Run the agora bootstrap. Returns the exit code."""
    agora_path = _agora_path_string()
    settings_path = paths.CLAUDE_SETTINGS_JSON

    settings = _load_settings()
    new_settings, diff = _plan_changes(settings, agora_path)

    if not diff:
        print("No changes needed to ~/.claude/settings.json (agora already registered).")
    else:
        for line in diff:
            print(line)
        print()
        if not yes and not _confirm("Apply changes? [y/N]: "):
            print("cancelled")
            return 0

        backup = _backup_settings(settings_path)
        content = json.dumps(new_settings, indent=2) + "\n"
        atomic_write(settings_path, content)
        if backup is not None:
            print(f"Wrote {settings_path} (backup at {backup.name})")
        else:
            print(f"Wrote {settings_path}")

    # Always run an initial compile so marketplace.json is fresh.
    # Pass paths explicitly so tests that monkeypatch paths.* take effect
    # (compile_to_disk's defaults were bound at its module-load time).
    compile_module.compile_to_disk(paths.PLUGINS_JSON, paths.MARKETPLACE_JSON)
    print("Compiled marketplace.json")

    print()
    print("Agora bootstrap complete.")
    print()
    print("Next steps:")
    print("  1. Restart Claude Code (or run /reload-settings).")
    print("  2. Open /plugins > Marketplaces > agora to browse plugins.")
    print("  3. Install plugins from the UI.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agora:setup",
        description=(
            "Register agora as a known marketplace in ~/.claude/settings.json "
            "and compile the initial marketplace.json."
        ),
    )
    parser.add_argument(
        "--yes",
        "-y",
        dest="yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    args = parser.parse_args(argv)
    return run_setup(yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())
