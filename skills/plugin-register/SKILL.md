---
name: agora:plugin-register
description: Use when registering a new plugin in agora or refreshing an existing entry to a newer release. Idempotent.
---

# plugin-register

Registers a plugin in agora's `plugins.json` or refreshes an existing entry to its latest stable release. Every field is derived from the plugin's GitHub repo — URL, latest tag and SHA, SPDX license, description, topics, homepage — and the registry plus generated `marketplace.json` are written atomically in one step.

## When to use

Call `plugin-register` after either:
- Tagging the **first release** of a plugin and wanting to add it to agora, or
- Tagging a **new release** of an already-registered plugin and wanting to bump its pinned version + SHA.

The same command serves both cases; if an entry with the derived `<owner>-<repo>` name already exists, it is overwritten in place (preserving `registered_at`).

## Prerequisites

The target plugin's repo must have:
1. A `LICENSE` file whose contents resolve to a recognized SPDX identifier (MIT, Apache-2.0, BSD-3-Clause, etc.). The GitHub-API SPDX value is used as a fallback when the local file is missing or unrecognized.
2. A non-empty GitHub repo **description**. Set it at `https://github.com/<owner>/<repo>/edit` or pass `--description`.
3. At least one **stable** SemVer release tag (e.g. `v1.0.0`). Pre-release tags (`-rc`, `-beta`) are excluded unless `--include-prerelease` is passed.

## Procedure

1. From the agora repo root, run one of:
   ```
   # cwd is the plugin repo (origin URL auto-detected):
   python scripts/plugin_register.py

   # explicit URL (any cwd):
   python scripts/plugin_register.py --url https://github.com/<owner>/<repo>.git

   # allow a -rc / -beta tag if no stable tag exists yet:
   python scripts/plugin_register.py --url ... --include-prerelease

   # override description or category:
   python scripts/plugin_register.py --description "Short tagline" --category development
   ```

2. On success the script prints `Registered <name> <version> (sha <short-sha>...)` followed by the git workflow needed to open a PR against agora.

3. On failure (missing license, empty GH description, no tags, GitHub API error, malformed URL) the script writes a single-line error to stderr and exits 1. Address the underlying cause and re-run.

## Hard rules

- **LICENSE is required.** If neither the local `LICENSE` file nor the GitHub API yields a recognized SPDX id (and not `NOASSERTION`), registration fails. Add a LICENSE file and re-tag.
- **GitHub description is required.** Plugins without a GH description are rejected; either set it on GitHub or pass `--description`.
- **The GitHub API is a hard dependency.** Network errors, 4xx/5xx responses, and persistent rate limits all fail the run. Set `GITHUB_TOKEN` or run `gh auth login` to raise the anonymous 60/hr limit.
- **Never hand-edit `marketplace.json`.** It is regenerated atomically by `registry.save_registry` whenever `plugins.json` is written.
- **Only stable tags by default.** Use `--include-prerelease` deliberately; the marketplace defaults to released versions.
