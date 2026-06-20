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
| CodeQL | **recommended** for code-bearing repos (advanced setup: committed `codeql.yml`, pinned SHAs) | extra static analysis beyond Ruff/Bandit. Runs for security alerts; **NOT** added to required status checks (advisory, never a merge gate) — matches agora's posture |
| Slow integration/e2e suites | **not** a required check | gating merges on a multi-minute e2e stalls the queue; run it on push/nightly or locally, keep the required gate fast (lint/type-check/unit) |

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
| loom | main | 1 (Lint & type-check) | ✅ **reconciled 2026-06-20** — slow e2e dropped from CI; fast `Lint & type-check` gate (eslint baseline: 17,344→0 errors, 99.86% config artifact) + required; CodeQL added (advisory) |
| loom-agent-chat | master | 1 (Lint & format (Ruff)) | ✅ **reconciled 2026-06-20** — added Ruff CI gate + `pyproject.toml`, CodeQL (advisory), branch protection (1 review, strict=false), and fixed `dbm`→true |

**CodeQL backfill (advisory, 2026-06-20):** added to every code-bearing own repo
that lacked it — atelier, kaizen, memex (python), web-harvester (js/ts),
second-brain-blueprint (python), loom (js/ts), loom-agent-chat (python). agora
already had it. The two bash repos (laravel-settler-lite, sail-new) are exempt —
CodeQL does not support shell/HCL/PowerShell. CodeQL is **never** a required
status check (advisory only).

### Forks — all compliant with Template B (no protection, no imposed wiring)
Understand-Anything · andrej-karpathy-skills · ladybug · skills

---

## Reconciliation plan

### 1. loom — DONE (2026-06-20, PR #5)
The only `pull_request`-triggered workflow was the **slow** `Playwright Electron
e2e` (~minutes). Per the "slow suites aren't required" rule, it was **deleted
from CI** (run locally; the 3 installer workflows are push-only and stay), and
replaced with a fast `Type-check` gate + CodeQL:
- deleted `.github/workflows/e2e.yml`
- added `ci.yml` → check-run **`Type-check`** (`npm ci` + `tsc --noEmit` ×2; ~40s)
- added `codeql.yml` (advanced setup; `actions` + `javascript-typescript`)
- branch protection now requires `Type-check` (strict=false, 1 review,
  enforce_admins=false); CodeQL runs advisory.

**Lint — DONE (2026-06-20, PR #9).** The "17,344 problems" was **99.86% config
artifact** (core `no-undef` on TS + linting `dist/`/design-mockups/sample
fixtures). A correct typescript-eslint flat config (TS parser, area-scoped
browser/node/electron globals, proper `ignores`) yielded **24 real → 0 errors /
43 advisory warnings**. Fixed 3 genuine issues (incl. a rules-of-hooks bug in
`ReceiptStrip`); tuned noisy rules with inline justifications; a11y left advisory.
The gate check-run was renamed **`Type-check` → `Lint & type-check`** and branch
protection updated to require the new name. *(Lesson: a giant lint count on a
clean-typechecking codebase is almost always a config artifact — fix the config
before touching code.)*

> ⚠️ `gh api -F 'required_status_checks[...]'` nested-field form silently drops
> `required_status_checks` (leaves it null). Send a JSON body via
> `gh api -X PUT ... --input <file>` instead:
> `{"required_status_checks":{"strict":false,"contexts":["Type-check"]},"enforce_admins":false,"required_pull_request_reviews":{"required_approving_review_count":1},"restrictions":null}`

### 2. loom-agent-chat — DONE (2026-06-20, PR #3) — chose path (b)
It had no CI and an anomalous protected-but-empty state. Applied the full
treatment: created `pyproject.toml` (was absent) + a Ruff CI gate (check-run
**`Lint & format (Ruff)`**, lint-only — no tests exist in the stdlib client),
added CodeQL (python+actions, advisory), set branch protection to require the
Ruff check (1 review, strict=false, enforce_admins=false), and fixed
`delete_branch_on_merge` false→true. Safe source fixes only (UP041 socket
timeout, 2× B904); UP031 %-format excluded with rationale.

### 3. CodeQL backfill — DONE (2026-06-20)
Added advisory CodeQL to every code-bearing own repo lacking it (atelier, kaizen,
memex, web-harvester, second-brain-blueprint, loom, loom-agent-chat). Bash repos
(laravel-settler-lite, sail-new) exempt — CodeQL has no shell support.

### 4. Everything else — no action
The remaining own repos and all 4 forks already match their template.

---

## Open decisions (resolved 2026-06-20)
1. ~~loom-agent-chat path~~ → **(b)** full CI + protection. Done.
2. ~~CodeQL backfill~~ → **done** across all code-bearing own repos.
3. **Required reviews = 1** kept as the uniform posture (solo-maintainer merges via
   the owner/admin path; `enforce_admins=false` enables it). Revisit to 0 only if
   that friction outweighs the gate's value.
