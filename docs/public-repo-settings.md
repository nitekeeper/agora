# Public repo settings — templates & reconciliation

Canonical settings posture for `nitekeeper`'s public GitHub repos. Two templates:
**A — Own repos** (authored here) and **B — Forks** (cloned from an upstream).
Audited 2026-06-20.

Apply via the GitHub REST API (`gh api`). The single most important rule:
**branch-protection `contexts` are CI _check-run names_, NOT workflow job ids.**
Using job ids (`lint`/`tests`) requires checks that never report and blocks every
merge. Read the names from a recent PR: `gh pr checks <n> --repo nitekeeper/<r>`.

---

## Template A — Own repos

For repos we author and release.

| Setting | Value | Why |
|---|---|---|
| Branch protection | **on** (default branch) | the actual merge gate |
| Required status checks | **all of the repo's PR-triggered check-run names** | green CI before merge; push-only/release workflows are NOT required |
| `strict` (up-to-date before merge) | **false** | avoids rebase-churn on every intervening merge; CI re-runs on the head anyway |
| Required reviews | **1** | a deliberate gate. NOTE: solo-maintainer ⇒ you can't approve your own PR, so merges use the owner/`--admin` path. `enforce_admins=false` (below) is what keeps that possible. If the friction isn't worth it on a given repo, 0 is acceptable — CI still gates. |
| `enforce_admins` | **false** | lets the maintainer `--admin`-merge when CI is green but no second reviewer exists |
| `delete_branch_on_merge` | **true** | merged branches auto-clean |
| `allow_auto_merge` | **false** | bump/release PRs are merged on manual review, not auto |
| CodeQL | **recommended** for code-bearing repos (advanced setup: committed `codeql.yml`, pinned SHAs) | extra static analysis beyond Ruff/Bandit; optional, not a hard gate |

**Apply (own repo `R`, default branch `B`, with its real check-run names):**
```bash
gh api -X PUT repos/nitekeeper/$R/branches/$B/protection \
  -F 'required_status_checks[strict]=false' \
  -F 'required_status_checks[contexts][]=<Check Run Name 1>' \
  -F 'required_status_checks[contexts][]=<Check Run Name 2>' \
  -F enforce_admins=false \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F restrictions=
gh api -X PATCH repos/nitekeeper/$R -F delete_branch_on_merge=true -F allow_auto_merge=false
```

---

## Template B — Forks

For repos forked from an upstream we track.

| Setting | Value | Why |
|---|---|---|
| Branch protection | **none** | protection blocks the force-push/rebase you need to re-sync from upstream |
| Required checks / reviews | **none** | don't gate code we don't own; PRs here are rare |
| CI / CodeQL / release wiring | **inherit upstream's** | don't add our own gatekeepers |
| `delete_branch_on_merge` | leave default (**false**) | lightweight; nothing to clean on a tracking fork |
| `allow_auto_merge` | **false** | n/a |

**Principle:** keep forks hands-off so they track upstream cleanly. No `gh api`
protection calls.

---

## Compliance audit (2026-06-20)

### Own repos
| Repo | Branch | Req. checks | Compliant? |
|---|---|---|---|
| agora | main | 3 (Ruff/Bandit/Tests) | ✅ |
| atelier | main | 3 (Ruff/Bandit/Tests) | ✅ |
| kaizen | main | 3 (Ruff/Bandit/Tests) | ✅ |
| memex | main | 3 (Ruff/Bandit/Tests) | ✅ |
| web-harvester | main | 3 (Fast/Medium/Slow Checks) | ✅ |
| laravel-settler-lite | main | 1 (ShellCheck) | ✅ (only PR check) |
| sail-new | main | 1 (ShellCheck) | ✅ (only PR check) |
| second-brain-blueprint | master | 1 (Markdown lint) | ✅ (only PR check) |
| **loom** | main | **0** | ❌ has `Playwright Electron e2e` PR check, requires none |
| **loom-agent-chat** | master | **0** | ❌ anomalous: protected, 0 checks, 0 reviews, `enforce_admins=true`, `dbm=false`, no CI |

### Forks — all compliant with Template B (no protection, no imposed wiring)
Understand-Anything · andrej-karpathy-skills · ladybug · skills

---

## Reconciliation plan

### 1. loom — require its PR check (the one real gap)
`e2e.yml` is the only `pull_request`-triggered workflow; its check-run is
`Playwright Electron e2e`. The 3 installer workflows are `push`-only release
builds and must NOT be required.
```bash
gh api -X PUT repos/nitekeeper/loom/branches/main/protection \
  -F 'required_status_checks[strict]=false' \
  -F 'required_status_checks[contexts][]=Playwright Electron e2e' \
  -F enforce_admins=false \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F restrictions=
```

### 2. loom-agent-chat — normalize (decision needed)
No CI workflows exist, so check-based protection isn't possible yet. Two paths:
- **(a) Lightweight now:** drop the anomalous state — `enforce_admins=false`,
  `delete_branch_on_merge=true`, keep 1 review (or 0). Add CI later.
  ```bash
  gh api -X PUT repos/nitekeeper/loom-agent-chat/branches/master/protection \
    -F enforce_admins=false \
    -F 'required_pull_request_reviews[required_approving_review_count]=1' \
    -F 'required_status_checks[strict]=false' -F restrictions=
  gh api -X PATCH repos/nitekeeper/loom-agent-chat -F delete_branch_on_merge=true
  ```
- **(b) Full:** add a minimal CI workflow (lint/test for the stdlib client), then
  apply Template A requiring its check-run name. Preferred long-term.

### 3. Everything else — no action
The 8 compliant own repos and all 4 forks already match their template.

### Optional — CodeQL backfill
Only agora (own) has `codeql.yml`. Adding it to the other code-bearing own repos
(kaizen/atelier/memex already track this in their TODOs) is recommended but not a
hard gate.

---

## Open decisions (carry into application)
1. **loom-agent-chat:** path (a) lightweight or (b) add CI? (default: (a) now, (b) later)
2. **CodeQL backfill** across own code repos — do it now or leave to each repo's TODO?
3. **Required reviews = 1** is the current uniform posture; revisit to 0 if the
   solo-maintainer `--admin` friction isn't worth it.
