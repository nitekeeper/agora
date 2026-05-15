---
name: agora-compile
description: Use when plugins.json has been edited by hand and the generated marketplace.json needs to be refreshed. Translates plugins.json -> .claude-plugin/marketplace.json.
---

# compile

Regenerates `.claude-plugin/marketplace.json` from `plugins.json`. `plugins.json` is the human-edited source of truth for the agora marketplace; `marketplace.json` is the generated artifact Claude Code's `/plugins > Marketplaces` UI reads, and it is gitignored.

## When to use

Call `compile` after hand-editing `plugins.json` (for example, fixing a typo, tweaking a description, or reordering plugins). All write skills — `plugin-register`, `plugin-unregister`, and `update` — invoke compile automatically as part of their atomic two-file write, so manual invocation is only needed for ad-hoc edits to `plugins.json`.

## Procedure

1. From the agora repo root, run:
   ```
   python scripts/compile.py
   ```
2. On success the script prints `Compiled <N> plugins -> .claude-plugin/marketplace.json` and exits 0.
3. On failure (missing or malformed `plugins.json`, missing required fields) the script writes a single-line error to stderr and exits 1. Fix `plugins.json` and re-run.

## Hard rules

- Never hand-edit `.claude-plugin/marketplace.json`. It is regenerated and gitignored.
- Always run `agora:validate` after a manual edit and compile so schema and uniqueness checks pass before Claude Code reads the result.
