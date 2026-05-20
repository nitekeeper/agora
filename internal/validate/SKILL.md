---
description: Use when plugins.json has been hand-edited and you want to lint it before committing, or when CI needs to verify the registry is well-formed.
---

# validate

Read-only structural validation of `plugins.json` against `docs/plugins.schema.json`, with an optional connectivity check that verifies each plugin's git URL / tag / SHA actually resolves on the remote. Never mutates files.

## When to use

- After hand-editing `plugins.json` (typo fix, description tweak, reorder) and before committing.
- In CI to gate merges — fail the build when `plugins.json` drifts from the schema or contains duplicate entries.
- Before publishing a release, with `--connectivity`, to confirm every pinned `(version, sha)` pair still resolves on the upstream repo.

Write skills (`plugin-register`, `plugin-unregister`, `update`) should ideally call this internally before their atomic two-file write. They do not yet — that is an open enhancement.

## Modes

| Mode | Flag | What it checks |
|---|---|---|
| Structural (default) | _(none)_ | JSON Schema (Draft 2020-12) validity + plugin `name` uniqueness + `repository_url` uniqueness. Fast, no network. |
| Connectivity | `--connectivity` | Structural checks plus `git ls-remote --tags <repository_url>` per plugin, confirming the pinned tag exists and resolves to the pinned SHA. Requires `git` on PATH. |

## Procedure

1. From the agora repo root, run:
   ```
   python3 scripts/validate.py
   ```
   For release-time verification:
   ```
   python3 scripts/validate.py --connectivity
   ```
   For machine-readable output (CI, agent pipelines):
   ```
   python3 scripts/validate.py --json
   ```

2. On success the script prints `plugins.json is valid` (and `connectivity check passed` when `--connectivity` is set) and exits 0.

3. On any error the script prints one line per error in the form `[error] <location>: <message>` and exits 1. `<location>` is a JSON pointer like `/plugins/0/current_version`, or a descriptive label for cross-field checks (e.g. `/plugins (uniqueness)`).

## Hard rules

- Exit code 0 means valid; exit code 1 means invalid. `--json` only changes output format, never the exit code.
- This skill is read-only — it never writes `plugins.json`, `marketplace.json`, or any other file.
- Run `internal/validate/SKILL.md` after every manual edit to `plugins.json` and before every commit that touches it.
