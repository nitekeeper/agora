# Automation: push-based version-bump notifications

This doc walks plugin authors through wiring their plugin's release workflow to automatically bump the pinned version in agora's `plugins.json` whenever a new release is tagged.

## How it works

```
plugin repo                                          agora repo
─────────────────────────                            ──────────────────────
release published   ─────► repository_dispatch ────► .github/workflows/
(tag like v1.2.3)         (event: plugin-released)   plugin-update.yml fires
                          carries: plugin name
                                   + tag                          │
                                                                  ▼
                                                       runs scripts/update.py
                                                                  │
                                                       if pin changed:
                                                                  ▼
                                                       opens a PR with
                                                       the bump (CI gates
                                                       run on the PR)
```

The plugin author tags a release. Their workflow fires a `repository_dispatch` event at agora. Agora's `plugin-update.yml` receives it, runs the update script for that plugin, and opens a PR with the bump. The PR runs through agora's CI gates (lint, security, tests).

## Prerequisite: fine-grained PAT

GitHub's per-workflow `GITHUB_TOKEN` is scoped to the repository that owns the workflow. A workflow in `plugin-foo` cannot fire `repository_dispatch` against `agora`, even when both repos are owned by the same account. You need a fine-grained PAT that has cross-repo dispatch permission.

**One-time setup (do this once for all your plugins):**

1. Go to GitHub → *Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token*.
2. Name it something like `agora-dispatch`. Set an expiry (90 days, 1 year — your call).
3. **Repository access:** *Only select repositories* → choose `nitekeeper/agora` (not your plugin repos).
4. **Repository permissions:** set **Contents: Read-only** and **Metadata: Read-only**. Leave everything else as *No access*.
5. Generate the token and copy it. You will not see it again.

**Per plugin repo:**

1. Go to the plugin repo → *Settings → Secrets and variables → Actions → New repository secret*.
2. Name: `AGORA_DISPATCH_TOKEN`.
3. Value: paste the PAT from above.

## Plugin-side workflow template

Add this to each plugin repo as `.github/workflows/notify-agora.yml`:

```yaml
name: Notify agora of release

on:
  release:
    types: [published]

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - name: Fire repository_dispatch at agora
        env:
          GH_TOKEN: ${{ secrets.AGORA_DISPATCH_TOKEN }}
        run: |
          # Plugin name is this repo's name in lowercase (matches agora's naming rules).
          plugin=$(echo "${{ github.event.repository.name }}" | tr 'A-Z' 'a-z')
          gh api repos/nitekeeper/agora/dispatches \
            -f event_type=plugin-released \
            -f client_payload[plugin]="$plugin" \
            -f client_payload[tag]="${{ github.event.release.tag_name }}"
```

That's the whole plugin-side piece. No build, no Python, no install — just a one-step GitHub CLI call.

## What happens end-to-end

1. You run `git tag vX.Y.Z && git push --tags` in a plugin repo.
2. You publish the release on GitHub (Releases → Draft → Publish; or use `gh release create vX.Y.Z`).
3. The plugin's `notify-agora.yml` workflow fires, sending a `repository_dispatch` to agora.
4. Agora's `plugin-update.yml` receives it within seconds, runs `scripts/update.py <plugin>`, and opens a PR titled `auto-update: bump <plugin> to vX.Y.Z`.
5. Agora's CI gates run on the PR.
6. You merge the PR.

If the plugin's version was already pinned to the new tag (e.g., you re-fired the dispatch), the workflow logs *No version change* and skips the PR.

## Limitations

- **Pre-release tags are skipped** by `agora:update` per agora's default policy. Firing a dispatch for a `v1.0.0-rc.1` tag still triggers the workflow, but the script logs "no version change" and no PR is opened. Pass `--include-prerelease` in the workflow if you want them.
- **Private plugin repos** require the dispatch token to have read access to the plugin repo too, so agora's `scripts/update.py` can fetch tags. Update the PAT's repository access list and re-set the secret.
- **Token rotation** — when the PAT expires, you'll see the plugin-side workflow fail with `Bad credentials`. Rotate the token in your GitHub account settings and re-paste it as `AGORA_DISPATCH_TOKEN` in each plugin repo.

## Alternative: pull-based (no PAT)

If you'd rather avoid the PAT setup, agora can poll instead — a scheduled workflow that runs `scripts/update.py --all` every 6 hours and opens PRs for whatever changed. That mode requires no plugin-side changes and no cross-repo auth. Trade-off: up to a 6-hour delay vs the push model's near-instant updates.

To enable the pull mode, you'd add a `.github/workflows/auto-update-poll.yml` to agora with a `schedule:` trigger. This repo doesn't ship one — choose whichever model fits your release cadence.
