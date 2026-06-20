# TODO

Deferred work tracked here so it survives session boundaries. Cross out items as they land or get explicitly dropped.

## When this repo goes public — DONE (flipped public 2026-06-19)

GitHub Pro features (branch protection, CodeQL) became free on the public repo and are wired up:

- [x] ~~**Enable branch protection on `main`**~~ — done. The required status checks are the three CI **check-run names** — `Lint & format (Ruff)`, `Security (Bandit + pip-audit)`, `Tests (pytest)` — NOT the job ids `lint`/`security`/`tests`. (An earlier draft of this item used the job ids as contexts; that would have required non-existent checks and blocked every merge.) Configured with `strict=true`, `enforce_admins=false`, no required reviews.
- [x] ~~**Bump PRs are opened automatically; the maintainer reviews + merges them**~~ — `plugin-update.yml` runs `scripts/update.py` and `gh pr create` on a `plugin-released` dispatch, opening an `auto-update/**` PR that runs the required CI gates. **Merge is manual review** — the maintainer reviews each bump PR and merges it by hand. (Repo `allow_auto_merge` is OFF.) An earlier iteration queued bump PRs for auto-merge via `gh pr merge "$branch" --auto --squash --delete-branch` and ran an `auto-update-health` scheduled watcher (#58) to flag stale open `auto-update/**` PRs; both were removed when the repo moved to manual review, since open bump PRs are now legitimately waiting for the maintainer rather than stuck.
- [x] ~~**Enable CodeQL**~~ — done (#53) via **advanced setup** (committed `.github/workflows/codeql.yml`; languages `python` + `actions`; action SHAs pinned per repo convention). GitHub's default-setup API returned 404 for the `gh` OAuth token, so advanced setup was used instead. To switch to zero-maintenance default setup later: delete `codeql.yml` and toggle Default on under Settings → Code security.

## Token hygiene

- [x] ~~**Set an expiry on `PLUGIN_REPOS_READ_TOKEN`**~~ — dropped. The plugin repos went public, so `git ls-remote` no longer needs authentication; the read-side PAT was removed from `plugin-update.yml` and its docs, the repo secret was deleted, and the `agora-plugin-read` PAT was revoked.

## Cleanup

- [x] ~~**Delete orphan branch `auto-update/memex-20260517-004102`**~~ — already gone; no `auto-update/**` branches remain on the remote.

## Cross-project parity

- [x] ~~**Atelier symmetry.**~~ — already wired: atelier has `ci.yml` + `release.yml` (whose "Notify agora marketplace" step dispatches `plugin-released` to agora via `AGORA_DISPATCH_TOKEN`) plus the dispatch-token secret. The auto-update chain from atelier is live (e.g. the v1.10.1 bump landed as #55).
