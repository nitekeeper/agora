---
name: agora:check
description: Use when refreshing the local "latest available version" cache for all registered plugins. Read by the session-start update banner.
---

# agora:check

Refreshes `~/.agora/check-cache.json` — the local cache of the highest semver tag available upstream for every plugin in `plugins.json`. The session-start update banner reads this cache so it can flag available upgrades without going to the network on every prompt.

## When to use

- Manual refresh when you want an up-to-the-minute view of which plugins have new releases (e.g. before running `agora:list --check`).
- Almost never as an explicit step — the session-start hook calls this automatically when the cache is missing or stale.

## Procedure

Run from the agora repo root.

### Default — `python scripts/check.py`

Honors a 24-hour TTL. If `~/.agora/check-cache.json` exists and was refreshed less than 24 hours ago, prints `cache is fresh (refreshed N hours ago); use --force to refresh anyway` and exits 0 without any git calls.

Otherwise, iterates every plugin in `plugins.json`, runs `git ls-remote --tags <repository_url>`, picks the highest semver tag, and writes the result to `~/.agora/check-cache.json`. Progress is printed one line per plugin:

```
  atelier: v1.3.0
  memex: ERROR (git ls-remote failed)
Checked 2 plugin(s) — 1 outdated, 1 errors.
```

### `--force`

Ignore the TTL and refresh anyway. Use after publishing a new release upstream when you want the local view to reflect it immediately.

### `--include-prerelease`

By default `pick_latest` skips tags with a prerelease suffix (e.g. `v2.0.0-rc1`). Pass `--include-prerelease` to consider them — useful for plugins that ship release candidates the user wants to track.

### `--json`

Emit the full cache dict to stdout as JSON instead of the human progress + summary. The cache file is still written. Suitable for piping into `jq` or feeding the result to another agent.

## Cache schema

`~/.agora/check-cache.json`:

```json
{
  "fetched_at": "2026-05-15T19:00:00Z",
  "include_prerelease": false,
  "plugins": {
    "atelier": {
      "latest_version": "v1.3.0",
      "checked_at": "2026-05-15T19:00:00Z"
    },
    "memex": {
      "latest_version": null,
      "error": "git ls-remote failed: ...",
      "checked_at": "2026-05-15T19:00:00Z"
    }
  }
}
```

- `fetched_at` — when the refresh began (ISO 8601 with `Z` suffix).
- `include_prerelease` — flag the cache was built under; consumers can decide whether to trust it for their query.
- `plugins[name].latest_version` — the picked tag, or `null` if `ls-remote` failed or no eligible tags exist.
- `plugins[name].error` — present only on failure; one-line message from `GitError`.
- `plugins[name].checked_at` — always present; timestamp of the per-plugin check.

## Exit codes

- `0` — success (including empty registry, fresh-cache short-circuit, and per-plugin errors recorded in the cache).
- Non-zero — only on argparse failures or unexpected exceptions (a malformed `plugins.json`, for instance).

## Hard rules

- Per-plugin `GitError` is recorded into the cache, never propagated. One broken plugin must not prevent the rest from being refreshed.
- The 24-hour TTL is enforced unless `--force` is set. Don't bypass it inside scripts — call `--force` explicitly so the bypass is visible.
- Always write the cache via `atomic.atomic_write` so concurrent reads (the session-start banner) never see a half-written file.
- Timestamps use `Z` suffix, not `+00:00`. Consumers parsing the cache rely on this.
