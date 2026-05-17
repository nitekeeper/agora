# TODO

Deferred work tracked here so it survives session boundaries. Cross out items as they land or get explicitly dropped.

## When this repo goes public

GitHub Pro features (branch protection, auto-merge, CodeQL) become free on public repos. Wire them up the moment the visibility flips:

- [ ] **Enable branch protection on `main`** so the CI gates actually block merges:
  ```bash
  gh api -X PUT repos/nitekeeper/agora/branches/main/protection \
    -F 'required_status_checks[strict]=true' \
    -F 'required_status_checks[contexts][]=lint' \
    -F 'required_status_checks[contexts][]=security' \
    -F 'required_status_checks[contexts][]=tests' \
    -F enforce_admins=false \
    -F required_pull_request_reviews= \
    -F restrictions=
  ```

- [ ] **Enable `allow_auto_merge` on the repo:**
  ```bash
  gh api -X PATCH repos/nitekeeper/agora -F allow_auto_merge=true
  ```

- [ ] **Teach `plugin-update.yml` to queue PRs for auto-merge.** Once `allow_auto_merge` is on and branch protection is configured, append a step after `gh pr create` that calls:
  ```bash
  gh pr merge "$branch" --auto --squash --delete-branch
  ```
  With both pieces in place, the auto-update PR self-merges as soon as the CI gates go green. The whole memex-release → agora-PR-merged chain becomes hands-off.

- [ ] **Enable CodeQL.** GitHub-hosted semantic analysis; free for public repos.

- [ ] (Optional) **Connect SonarCloud.** Useful for inline PR comments + dashboards.

## Token hygiene

- [ ] **Set an expiry on `PLUGIN_REPOS_READ_TOKEN`** — currently no-expiration. Industry standard is 1 year max for personal automation tokens. Regenerate via *Settings → Developer settings → Fine-grained tokens*, edit expiry to 365 days, re-paste as the same secret name in agora.

- [ ] **Confirm `AGORA_DISPATCH_TOKEN`'s expiry on each plugin repo** (memex, atelier) — should be 1 year per the setup walkthrough.

## Cleanup

- [ ] **Delete orphan branch `auto-update/memex-20260517-004102`.** Created by a failed `plugin-update.yml` run before the GHA bot was permitted to open PRs; the commit on it was superseded by the PR we eventually opened. Safe to remove:
  ```bash
  gh api -X DELETE repos/nitekeeper/agora/git/refs/heads/auto-update/memex-20260517-004102
  ```
  Or delete via the GitHub UI's *Branches* page.

## Cross-project parity

- [ ] **Atelier symmetry.** Atelier hasn't been wired into the push-loop yet — no CI gatekeepers, no `notify-agora` workflow, no `AGORA_DISPATCH_TOKEN` secret. When it ships its first real release, add the same setup we did for memex.
