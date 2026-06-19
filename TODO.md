# TODO

Deferred work tracked here so it survives session boundaries. Cross out items as they land or get explicitly dropped.

## When this repo goes public — DONE (flipped public 2026-06-19)

GitHub Pro features (branch protection, auto-merge, CodeQL) became free on the public repo; all are wired up:

- [x] ~~**Enable branch protection on `main`**~~ — done. The required status checks are the three CI **check-run names** — `Lint & format (Ruff)`, `Security (Bandit + pip-audit)`, `Tests (pytest)` — NOT the job ids `lint`/`security`/`tests`. (An earlier draft of this item used the job ids as contexts; that would have required non-existent checks and blocked every merge.) Configured with `strict=true`, `enforce_admins=false`, no required reviews.
- [x] ~~**Enable `allow_auto_merge` on the repo**~~ — done.
- [x] ~~**Teach `plugin-update.yml` to queue PRs for auto-merge**~~ — done (#52). After `gh pr create`, the workflow runs `gh pr merge "$branch" --auto --squash --delete-branch` (made non-fatal so a transient failure can't lose the bump PR). Verified hands-off end to end: bot PRs #55/#56 ran the required CI and auto-merged with no human. This works because **"Allow GitHub Actions to create and approve pull requests"** (`can_approve_pull_request_reviews`) is enabled — bot PRs created before that setting (e.g. #44/#45/#46) parked their checks as `action_required` and had to be merged by hand. Caveat: if a future bot PR ever parks its required checks, `--auto` enables but never completes (silent hang) — the `auto-update-health` scheduled workflow (#58) flags any stale open `auto-update/**` PR via a tracking issue.
- [x] ~~**Enable CodeQL**~~ — done (#53) via **advanced setup** (committed `.github/workflows/codeql.yml`; languages `python` + `actions`; action SHAs pinned per repo convention). GitHub's default-setup API returned 404 for the `gh` OAuth token, so advanced setup was used instead. To switch to zero-maintenance default setup later: delete `codeql.yml` and toggle Default on under Settings → Code security.

## Token hygiene

- [x] ~~**Set an expiry on `PLUGIN_REPOS_READ_TOKEN`**~~ — dropped. The plugin repos went public, so `git ls-remote` no longer needs authentication; the read-side PAT was removed from `plugin-update.yml` and its docs, the repo secret was deleted, and the `agora-plugin-read` PAT was revoked.

## Cleanup

- [x] ~~**Delete orphan branch `auto-update/memex-20260517-004102`**~~ — already gone; no `auto-update/**` branches remain on the remote.

## Cross-project parity

- [x] ~~**Atelier symmetry.**~~ — already wired: atelier has `ci.yml` + `release.yml` (whose "Notify agora marketplace" step dispatches `plugin-released` to agora via `AGORA_DISPATCH_TOKEN`) plus the dispatch-token secret. The auto-update chain from atelier is live (e.g. the v1.10.1 bump landed as #55).
