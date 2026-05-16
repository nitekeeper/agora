---
description: Use when working with the agora plugin marketplace — routes operations like plugin-register, update, check, validate, compile to the right internal procedure.
---

Agora is a custom Claude Code plugin marketplace. This skill is the public entry point — it maps user intent to the right internal procedure (read via the Read tool, follow inline).

## Internal procedures

All agora operations live as plain markdown procedure files at `internal/<name>/SKILL.md`. These are NOT Claude Code slash commands — they are reachable only via the Read tool. Whenever this skill references `internal/<name>/SKILL.md` below, the agent should: (1) Read that file, (2) follow the procedure inline. The 8 internal procedures are `compile`, `list`, `validate`, `plugin-register`, `plugin-unregister`, `update`, `check`, `setup`.

## Intent routing

When the user expresses one of these intents, read the corresponding internal procedure and follow it:

| User intent | Internal procedure |
|---|---|
| Register a new plugin (or refresh an existing entry) | `internal/plugin-register/SKILL.md` |
| Remove a plugin from the marketplace | `internal/plugin-unregister/SKILL.md` |
| Update one plugin (or all) to the latest stable release | `internal/update/SKILL.md` |
| Refresh the local "latest available version" cache | `internal/check/SKILL.md` |
| Regenerate `.claude-plugin/marketplace.json` from `plugins.json` | `internal/compile/SKILL.md` |
| Lint `plugins.json` (structural + optional connectivity check) | `internal/validate/SKILL.md` |
| List registered plugins (optionally with update status) | `internal/list/SKILL.md` |
| Bootstrap or re-bootstrap the agora install on a machine | `internal/setup/SKILL.md` |

## Conventions agora enforces

- Plugin names in `plugins.json` use the bare lowercase repo name (e.g. `atelier`, not `nitekeeper-atelier`).
- All Anthropic plugin-name rules apply: kebab-case lowercase, no spaces or special characters.
- Skills inside plugins follow Anthropic's convention: `description:` only in frontmatter; the slash command is auto-derived from `<plugin-name>:<dir-name>`.
- Source-of-truth is `plugins.json` at the agora repo root. `.claude-plugin/marketplace.json` is gitignored — it's a generated artifact rebuilt by `compile` (and automatically on every write op + on session-start staleness check).
- All write ops are atomic via `scripts/atomic.py` — both `plugins.json` and the recompiled `marketplace.json` are committed together or neither.
- Pre-release tags are skipped by default; pass `--include-prerelease` to opt in (applies to `plugin-register`, `update`, `check`).
- GitHub is a hard dependency. License detection requires either a LICENSE file in the plugin repo or a non-empty `license.spdx_id` from the GH API.

## Authority and override

User instructions override this skill's defaults at all times. If the user provides a direct instruction — "just run the script," "skip the check," or any unambiguous bypass directive — comply immediately without re-asking.

Priority order when instructions conflict:

1. **User's explicit instructions — highest priority.**
2. **Agora methodology (this skill).**
3. **Default system prompt.**
