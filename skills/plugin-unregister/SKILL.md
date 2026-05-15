---
name: agora:plugin-unregister
description: Use when removing a plugin entry from the agora marketplace registry. Consumers who already installed the plugin keep their cache until they uninstall via Claude Code's /plugins UI.
---

# plugin-unregister

Remove a plugin entry from `plugins.json` and re-compile `.claude-plugin/marketplace.json` in a single atomic dual-file write.

## When to use

- A plugin has been deprecated, renamed, or moved to a different marketplace and should no longer be listed.
- A registration was made in error and needs to be reverted before publication.
- You are pruning unmaintained entries during routine marketplace housekeeping.

Do NOT use this skill to "uninstall" a plugin for an existing consumer — Claude Code caches installed plugins locally. End users must remove it themselves via the `/plugins` UI.

## Procedure

1. From the agora repo root, run:
   ```
   python scripts/plugin_unregister.py <name>
   ```
   The script prints the matching entry and prompts `Remove this entry? [y/N]:`. Answer `y` / `Y` / `yes` to proceed; anything else cancels with no side effects.

2. To skip the prompt (CI, scripted use, agent-driven flows), pass `--yes`:
   ```
   python scripts/plugin_unregister.py <name> --yes
   ```

3. On success the script:
   - Atomically rewrites both `plugins.json` and `.claude-plugin/marketplace.json`.
   - Prints `Removed plugin '<name>'.`
   - Prints a git workflow hint for branching, committing, and opening a PR.

4. Follow the printed git workflow to land the change:
   ```
   git checkout -b unregister-<name>
   git add plugins.json
   git commit -m "Unregister <name>"
   git push -u origin unregister-<name>
   gh pr create
   ```

## Edge cases

- **Plugin not found.** Script prints `plugin not found: <name>` to stderr and exits 1. Neither file is modified.
- **Cancelled at prompt.** Script prints `cancelled` and exits 0. Neither file is modified.
- **Consumer caches.** Removing an entry from `plugins.json` does NOT uninstall the plugin from any consumer who has already added the marketplace. They keep their cached copy until they explicitly uninstall via `/plugins`. Communicate deprecations out-of-band when that matters.

## Hard rules

- Always run from the agora repo root so `scripts/paths.py` resolves the correct `plugins.json` and `marketplace.json`.
- The two-file write is atomic — never hand-edit `marketplace.json`; let `registry.save_registry()` regenerate it.
- After landing the PR, run `python scripts/validate.py` to confirm the registry is still well-formed.
