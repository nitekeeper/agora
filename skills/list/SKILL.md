---
description: Use when you want to see what plugins are registered in the local agora marketplace and optionally which ones have updates available.
---

# agora:list

Prints a summary of every plugin registered in `plugins.json`. Mirrors the look-and-feel of `brew list` / `apt list` / `npm list`: a two-space-separated columnar table by default, with optional `--check` for outdated-status and `--json` for machine consumption.

## When to use

- Quick local inventory: which plugins are tracked in this marketplace?
- Pre-update audit: `--check` reads the `agora:check` cache and shows which plugins have newer upstream releases.
- Scripting / piping: `--json` emits the raw plugin array suitable for `jq` and friends.

## Procedure

Run from the agora repo root.

### Default — `python scripts/list_plugins.py`

Prints a columnar table of registered plugins:

```
NAME        VERSION   LICENSE       CATEGORY
atelier     v1.0.0    MIT           development
memex       v0.3.1    Apache-2.0    productivity
```

Header is bolded via ANSI escape when stdout is a TTY; plain text when piped. Column widths are sized to the data with a small minimum so the header line aligns.

If `plugins.json` is empty, prints `(no plugins registered)`.

### Outdated check — `python scripts/list_plugins.py --check`

Reads `~/.agora/check-cache.json` (populated by `agora:check`) and adds `LATEST` / `STATUS` columns:

```
NAME        CURRENT   LATEST    STATUS
atelier     v1.0.0    v1.3.0    outdated
memex       v0.3.1    v0.3.1    up-to-date
```

Status values:

- `up-to-date` — `current_version` matches `latest_version` from cache
- `outdated` — versions differ
- `unknown` — no cache entry for this plugin

If the cache file is missing or malformed, a one-line warning is written to stderr (`agora:check cache not found at … — run python scripts/check.py to refresh`) and every row falls back to `unknown`. Cache problems never raise; they only degrade the output.

`--outdated` is accepted as an alias for `--check`.

### JSON — `python scripts/list_plugins.py --json`

Emits the `plugins[]` array verbatim to stdout. Combine with `--check` to augment each entry with `latest_version` and `status` keys. With an empty plugins array, emits `[]`.

## Exit codes

- `0` — success (including empty plugins or missing cache)
- `1` — `plugins.json` is missing or malformed (stderr message is printed)

## Hard rules

- Never raise on a missing or malformed check cache. Degrade to `unknown` rows and warn to stderr.
- Never colour the header when stdout is not a TTY — output must be pipe-safe.
- Default paths come from `scripts/paths.py` (`PLUGINS_JSON`, `CHECK_CACHE_JSON`). The `--plugins` and `--cache` flags exist for testing and override defaults.
