# scripts/plugin_unregister.py
"""agora:plugin-unregister — remove a plugin entry from plugins.json.

Looks up the plugin by name, prints the entry to be removed, asks for
confirmation (unless --yes is passed), deletes the entry, and atomically
re-compiles marketplace.json via registry.save_registry().
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support both `python -m scripts.plugin_unregister` and
# `python scripts/plugin_unregister.py` invocations by ensuring the repo
# root is on sys.path for the direct case.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import registry


def _git_workflow_hint(name: str) -> str:
    return (
        f"git checkout -b unregister-{name}; "
        f"git add plugins.json; "
        f'git commit -m "Unregister {name}"; '
        f"git push -u origin unregister-{name}; "
        f"gh pr create"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agora:plugin-unregister",
        description="Remove a plugin entry from the agora marketplace registry.",
    )
    parser.add_argument("name", help="Plugin name to remove (matches the 'name' field).")
    parser.add_argument(
        "--yes",
        "-y",
        dest="yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    args = parser.parse_args(argv)

    data = registry.load_registry()
    found = registry.find_plugin(data, args.name)
    if found is None:
        print(f"plugin not found: {args.name}", file=sys.stderr)
        return 1
    index, entry = found

    print(json.dumps(entry, indent=2))

    if not args.yes:
        try:
            response = input("Remove this entry? [y/N]: ")
        except EOFError:
            response = ""
        if response.strip().lower() not in ("y", "yes"):
            print("cancelled")
            return 0

    del data["plugins"][index]
    registry.save_registry(data)

    print(f"Removed plugin '{args.name}'.")
    print(_git_workflow_hint(args.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
