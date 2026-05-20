# Agora — Custom Plugin Marketplace

Agora is a self-hosted Claude Code plugin marketplace. It's a curated registry over Claude Code's native marketplace mechanism: each plugin lives in its own GitHub repository with semver release tags; agora holds a single source-of-truth index (`plugins.json`) at the repo root and compiles it into the `marketplace.json` shape Claude Code expects. Authors register their plugins via PRs; consumers clone agora, bootstrap it once, and use Claude Code's built-in `/plugins` UI to browse and install.

## A note on origins

Most of the code in this repository is developed and maintained collaboratively with [Claude Code](https://claude.com/claude-code). Commits are typically co-authored (`Co-Authored-By: Claude Opus …`), tests and refactors are AI-assisted, and design documents are pair-written. Human-authored PRs are welcome; when reviewing changes, apply the usual AI-codegen review reflexes — most of it is clean, but the occasional confident-but-wrong section is worth a careful read.

## How it works

- **Plugin repos** — one per plugin. They own their code, their `plugin.json`, and their release tags. Agora never edits them.
- **Agora repo** — this repo. Holds `plugins.json` (the human-edited registry) and the tooling that compiles it into `.claude-plugin/marketplace.json`.
- **Claude Code** — reads the generated `marketplace.json` and handles browse, search, install, enable, and disable through its native `/plugins > Marketplaces` UI.

## Installation

Agora has three audiences with different install paths.

### For consumers — using plugins from agora

You want to browse and install the plugins registered in agora through Claude Code's normal `/plugins` UI.

1. Clone the agora repo:

   ```bash
   git clone https://github.com/nitekeeper/agora.git
   ```

2. Bootstrap. This registers the marketplace in `~/.claude/settings.json`, compiles `plugins.json` into `marketplace.json`, validates every entry, and installs the session-start update banner:

   ```bash
   python3 scripts/setup.py
   ```

3. Open Claude Code → `/plugins > Marketplaces > agora` → browse and install.

4. Pull updates:

   ```bash
   git pull
   agora:update --all          # bump every pinned plugin
   agora:update <name>         # or bump one
   ```

### For plugin authors — registering your plugin

You want your plugin to appear in agora so consumers can install it via the `/plugins` UI.

**1. Prep the plugin repo**

- **Add a `LICENSE` file** with a recognized SPDX identifier (`MIT`, `Apache-2.0`, `BSD-3-Clause`, etc.). This is required — registration is a hard error if no license can be detected.
- **Set a GitHub repo description.** Agora uses it as the plugin description. If it's missing, `agora:plugin-register` will prompt you for one.
- **Add GitHub topics** for category and keywords. Optional but recommended; agora maps them against its taxonomy.
- **Add a `plugin.json`** per Claude Code's plugin schema. Claude Code reads this after install — agora itself never reads it.

**2. Tag a release**

```bash
git tag vX.Y.Z
git push --tags
```

Use semver. Pre-release tags (`-rc.1`, `-beta`, `-alpha`) are skipped by default — see [Pre-release policy](#pre-release-policy).

**3. Register with agora**

```bash
git clone https://github.com/nitekeeper/agora.git
cd agora

# From inside your plugin repo (helper reads `git remote get-url origin`):
cd /path/to/your/plugin
agora:plugin-register

# Or register a remote plugin without cloning it:
cd /path/to/agora
agora:plugin-register --url https://github.com/<owner>/<repo>.git
```

`agora:plugin-register` is idempotent: re-running on an existing entry refreshes the version and metadata.

**4. Submit a PR**

Open a pull request against `nitekeeper/agora` with the updated `plugins.json`. Direct pushes to `main` are blocked.

**(Optional) Wire up automatic bumps on future releases**

After your plugin is registered, you can set up a one-time hook so future releases auto-bump the pin in agora. Each new release in your plugin repo fires a GitHub `repository_dispatch` event at agora; agora's `plugin-update.yml` workflow receives it, runs `scripts/update.py <your-plugin>`, and opens a PR with the new pin. The PR goes through agora's CI gates before merging.

Setup is ~5 minutes per plugin (a fine-grained PAT + a 20-line workflow file). See [docs/automation.md](docs/automation.md) for the full walkthrough.

### For agora contributors — working on agora itself

You want to hack on the marketplace tooling, fix bugs in the registry compiler, or send PRs.

```bash
git clone https://github.com/nitekeeper/agora.git
cd agora
pip install -r requirements.txt
pip install pytest ruff bandit pip-audit      # dev tooling
pytest tests/                                  # ~220 tests
ruff check . && ruff format --check .          # lint + format
bandit -c pyproject.toml -r scripts hooks internal   # security
```

PRs run a CI gate (lint, security, tests) — see `.github/workflows/ci.yml`. Once the repo is configured with branch protection on `main`, merges require all three checks green.

Code layout you'll probably touch:

- `plugins.json` — the human-edited registry (source of truth).
- `scripts/` — the registry-compilation and plugin-management tooling (`setup.py`, `compile.py`, `update.py`, `plugin_register.py`, `validate.py`, etc.).
- `tests/` — pytest suite covering the script primitives, schema, and session-start hook.
- `hooks/session_start.py` — the update-available banner.
- `skills/agora/SKILL.md` — the user-facing skill that fronts the registry operations.
- `docs/` — design docs and conventions.

## Plugin naming

Plugin names use the bare `<repo>` name (lowercase, `.git` stripped).

Example: `github.com/nitekeeper/atelier` → plugin name `atelier`.

Names must be lowercase alphanumeric plus dot and dash. Because the owner is dropped, two plugins from different owners with the same repo name would collide; agora is currently single-owner, so this is acceptable. Agora stores the source git URL as the real anchor.

## Field derivation

Agora reads every `plugins.json` field from the git repo and the GitHub API. Authors don't maintain agora-specific files.

| Field | Sourced from |
|---|---|
| `name` | URL path → `<repo>` (lowercase) |
| `repository_url` | The URL |
| `current_version` | Latest stable git tag |
| `current_sha` | Tag → commit resolution |
| `description` | GitHub repo description (prompts if missing) |
| `license` | LICENSE file (SPDX-parsed); GH API fallback. **Hard error if not detected.** |
| `category`, `keywords` | GH topics (mapped against the agora taxonomy) |
| `author`, `homepage` | GH API |

## Skill commands

| Command | Audience | Purpose |
|---|---|---|
| `agora:setup` | Consumer | One-time machine setup |
| `agora:plugin-register [--url URL]` | Author | Register or refresh a plugin entry |
| `agora:plugin-unregister <name>` | Author | Remove a plugin entry |
| `agora:compile` | Maintainer | Re-translate `plugins.json` → `marketplace.json` |
| `agora:update <name>` / `agora:update --all` | Consumer | Bump pinned versions |
| `agora:check` | Consumer | Refresh "available versions" cache |
| `agora:list` | Consumer | Show registered plugins + versions |
| `agora:validate` | Anyone | Lint `plugins.json` (also runs in CI) |

Claude Code's native `/plugins` UI handles browse, search, install, and enable/disable — agora does not duplicate those.

## Pre-release policy

Stable-only by default. Tags with pre-release identifiers (`-rc1`, `-beta.3`, `-alpha`) are ignored by `agora:plugin-register`, `agora:update`, and `agora:check`. Pass `--include-prerelease` to opt in.

A plugin with only pre-release tags fails `agora:plugin-register` with a clear error suggesting either tagging a stable release or passing the flag.

This matches the default behavior of npm, cargo, and pip.

## Updates

- **User-initiated only.** Agora never auto-upgrades — version bumps don't happen mid-session. The session-start banner only *announces* available updates; you decide when to apply them with `agora:update`.
- **Session-start banner** announces pending updates, read from a local cache populated by `agora:check`. Example: `atelier  v1.2.0 → v1.3.0`. The banner is quiet and dismissible.
- **Opportunistic cache refresh.** The session-start hook keeps the cache fresh in the background: if the cache is missing or older than 1 hour, it spawns a detached `agora:check` subprocess. The subprocess runs fully backgrounded — no console window, no blocking session start. The banner reflects the latest data on your next session.
- **Cache TTL ~24h** at the `agora:check` layer. Offline runs fall back to the last known cache silently.
- **Optional push-based bumps.** Plugin authors can wire their release workflow to fire a `repository_dispatch` event at agora; agora then opens a PR with the bump within seconds. Setup walkthrough at [docs/automation.md](docs/automation.md).

## Repository layout

```
agora/
  .claude-plugin/
    marketplace.json       # generated from plugins.json
  plugins.json             # human-edited registry, source of truth
  scripts/
    setup.py
    compile.py
    update.py
    check.py
    plugin_register.py
  tests/
  hooks/
    session_start.py       # update-available banner
  skills/
    agora/
      SKILL.md
  docs/
    automation.md          # plugin-author guide: push-based version bumps
  .github/
    workflows/
      ci.yml               # lint + security + tests, runs on every PR
      plugin-update.yml    # receives repository_dispatch from plugin repos
    dependabot.yml         # weekly pip + github-actions updates
  README.md
```

## Naming

Greek `agora` = public marketplace and gathering place. Matches the convention of related sibling projects (memex, atelier) — name a place, not a function.
