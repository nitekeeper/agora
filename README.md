# Agora — Custom Plugin Marketplace

Agora is a self-hosted Claude Code plugin marketplace. It's a curated registry over Claude Code's native marketplace mechanism: each plugin lives in its own GitHub repository with semver release tags; agora holds a single source-of-truth index (`plugins.json`) at the repo root and compiles it into the `marketplace.json` shape Claude Code expects. Authors register their plugins via PRs; consumers clone agora, bootstrap it once, and use Claude Code's built-in `/plugins` UI to browse and install.

## A note on origins

Most of the code in this repository is developed and maintained collaboratively with [Claude Code](https://claude.com/claude-code). Commits are typically co-authored (`Co-Authored-By: Claude Opus …`), tests and refactors are AI-assisted, and design documents are pair-written. Human-authored PRs are welcome; when reviewing changes, apply the usual AI-codegen review reflexes — most of it is clean, but the occasional confident-but-wrong section is worth a careful read.

## How it works

- **Plugin repos** — one per plugin. They own their code, their `plugin.json`, and their release tags. Agora never edits them.
- **Agora repo** — this repo. Holds `plugins.json` (the human-edited registry) and the tooling that compiles it into `.claude-plugin/marketplace.json`. The compiled `marketplace.json` is committed and tracked in the repo (not gitignored), so a fresh clone already has it.
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

4. Pull updates, then ask `agora:run` to apply them:

   ```bash
   git pull
   ```

   Then invoke the `agora:run` skill and express your intent in natural language — for example "update all plugins to the latest stable release" (bumps every pinned plugin) or "update atelier" (bumps one). `agora:run` routes the request to the right internal operation.

### For plugin authors — registering your plugin

You want your plugin to appear in agora so consumers can install it via the `/plugins` UI.

**1. Prep the plugin repo**

- **Add a `LICENSE` file** with a recognized SPDX identifier (`MIT`, `Apache-2.0`, `BSD-3-Clause`, etc.). This is required — registration is a hard error if no license can be detected.
- **Set a GitHub repo description.** Agora uses it as the plugin description. If it's missing, the register operation will prompt you for one.
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
```

Then invoke the `agora:run` skill and express your intent — "register a plugin". It routes to the internal `plugin-register` operation, which can either:

- read your plugin from the current directory (it reads `git remote get-url origin`), so run it from inside your plugin repo; or
- register a remote plugin without cloning it — tell it the repo URL (e.g. "register the plugin at https://github.com/&lt;owner&gt;/&lt;repo&gt;.git").

Registration is idempotent: re-running on an existing entry refreshes the version and metadata.

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
pytest tests/                                  # the full test suite
ruff check . && ruff format --check .          # lint + format
bandit -c pyproject.toml -r scripts hooks internal   # security
```

PRs run a CI gate (lint, security, tests) — see `.github/workflows/ci.yml`. CodeQL static analysis (`.github/workflows/codeql.yml`) also runs on every PR (plus a weekly schedule), scanning the `python` and GitHub `actions` code. Once the repo is configured with branch protection on `main`, merges require all three checks green.

Code layout you'll probably touch:

- `plugins.json` — the human-edited registry (source of truth).
- `scripts/` — the registry-compilation and plugin-management tooling (`setup.py`, `compile.py`, `update.py`, `plugin_register.py`, `validate.py`, etc.).
- `tests/` — pytest suite covering the script primitives, schema, and session-start hook.
- `hooks/session_start.py` — the update-available banner.
- `skills/run/SKILL.md` — the public `agora:run` skill that routes natural-language intents to the internal operations.
- `internal/` — the 8 operation procedures (`setup`, `compile`, `update`, `check`, `list`, `validate`, `plugin-register`, `plugin-unregister`), each at `internal/<name>/SKILL.md`. Reached only via `agora:run`, never invoked as slash commands.
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

Beyond the per-plugin entries above, `plugins.json` also carries a top-level `marketplace` metadata object (`name`, `description`, `owner`). This seeds the corresponding marketplace-level fields in the compiled `marketplace.json`.

## Operations

Agora exposes a **single** Claude Code skill: `agora:run`. There are no `agora:<verb>` slash commands. You invoke `agora:run` and describe what you want in natural language; the skill routes your intent to one of the internal operation procedures below (each lives at `internal/<name>/SKILL.md` and is reached only via `agora:run`, never invoked directly).

| Internal operation | Audience | Example intent for `agora:run` | Purpose |
|---|---|---|---|
| `setup` | Consumer | "bootstrap agora on this machine" | One-time machine setup |
| `plugin-register` | Author | "register a plugin" (optionally with a repo URL) | Register or refresh a plugin entry |
| `plugin-unregister` | Author | "remove plugin &lt;name&gt;" | Remove a plugin entry |
| `compile` | Maintainer | "compile the marketplace" | Re-translate `plugins.json` → `marketplace.json` |
| `update` | Consumer | "update all plugins" / "update &lt;name&gt;" | Bump pinned versions |
| `check` | Consumer | "check for updates" | Refresh "available versions" cache |
| `list` | Consumer | "list registered plugins" | Show registered plugins + versions |
| `validate` | Anyone | "validate plugins.json" | Lint `plugins.json` (also runs in CI) |

Claude Code's native `/plugins` UI handles browse, search, install, and enable/disable — agora does not duplicate those.

## Pre-release policy

Stable-only by default. Tags with pre-release identifiers (`-rc1`, `-beta.3`, `-alpha`) are ignored by the `plugin-register`, `update`, and `check` operations. Pass `--include-prerelease` to opt in.

A plugin with only pre-release tags fails the `plugin-register` operation with a clear error suggesting either tagging a stable release or passing the flag.

This matches the default behavior of npm, cargo, and pip.

## Updates

- **User-initiated only.** Agora never auto-upgrades — version bumps don't happen mid-session. The session-start banner only *announces* available updates; you decide when to apply them by asking `agora:run` to update.
- **Session-start banner** announces pending updates, read from a local cache populated by the `check` operation. Example: `atelier  v1.2.0 → v1.3.0`. The banner is quiet and dismissible.
- **Opportunistic cache refresh.** The session-start hook keeps the cache fresh in the background: if the cache is missing or older than 1 hour, it spawns a detached check subprocess (`scripts/check.py`). The subprocess runs fully backgrounded — no console window, no blocking session start. The banner reflects the latest data on your next session.
- **Cache TTL ~24h** at the check layer. Offline runs fall back to the last known cache silently.
- **Optional push-based bumps.** Plugin authors can wire their release workflow to fire a `repository_dispatch` event at agora; agora then opens a PR with the bump within seconds. Setup walkthrough at [docs/automation.md](docs/automation.md).

## Repository layout

```
agora/
  .claude-plugin/
    marketplace.json       # compiled from plugins.json; committed/tracked (not gitignored)
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
    run/
      SKILL.md             # public agora:run skill — routes intents to internal ops
  internal/                # operation procedures, reached only via agora:run (not slash commands)
    setup/SKILL.md
    compile/SKILL.md
    update/SKILL.md
    check/SKILL.md
    list/SKILL.md
    validate/SKILL.md
    plugin-register/SKILL.md
    plugin-unregister/SKILL.md
  docs/
    automation.md          # plugin-author guide: push-based version bumps
  .github/
    workflows/
      ci.yml               # lint + security + tests, runs on every PR
      codeql.yml           # CodeQL static analysis (python + actions), PR + weekly
      plugin-update.yml    # receives repository_dispatch from plugin repos
    dependabot.yml         # weekly pip + github-actions updates
  README.md
```

## Naming

Greek `agora` = public marketplace and gathering place. Matches the convention of related sibling projects (memex, atelier) — name a place, not a function.
