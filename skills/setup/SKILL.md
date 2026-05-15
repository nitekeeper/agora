---
name: agora-setup
description: Use when registering agora in ~/.claude/settings.json after the initial install — useful for re-running bootstrap on a second machine, after settings.json corruption, or after the agora repo has been moved. For the very first install, run `python scripts/setup.py` directly from the agora directory.
---

# agora-setup

Re-runs the agora bootstrap, which registers the agora marketplace in `~/.claude/settings.json` under `extraKnownMarketplaces.agora` and triggers an initial compile. Wraps `scripts/setup.py` for discoverable post-install invocation.

## When to use

- Re-registering agora on a second machine that shares the same checkout (or a fresh checkout on the same machine for a second user).
- Recovering after `~/.claude/settings.json` was corrupted, hand-edited incorrectly, or wiped.
- Re-pointing the registration after the agora repo has been moved to a new path.

## When NOT to use

- For the very first install on a machine. The skill isn't loaded until agora is registered, so the initial bootstrap must invoke the script directly: `python scripts/setup.py` from the agora directory.

## Procedure

1. `cd` into the agora repo root.
2. Run:
   ```
   python scripts/setup.py
   ```
   Or, to skip the interactive confirmation:
   ```
   python scripts/setup.py --yes
   ```
3. Review the printed diff against `~/.claude/settings.json` and confirm.
4. Restart Claude Code (or run `/reload-settings`) so the new marketplace registration takes effect.

## Hard rules

- The skill only writes the `extraKnownMarketplaces.agora` entry in `~/.claude/settings.json`. All other keys are preserved.
- A timestamped backup (`settings.json.bak.<ts>`) is created before any overwrite.
- The script refuses to run if `~/.claude/settings.json` exists but is not valid JSON — fix it manually first, then re-run.
