---
name: gitgud-ci
description: One-time GitHub setup so every PR is checked before it reaches main - a GitHub Actions workflow for test, lint and build matching the detected stack (actions pinned by commit SHA, read-only token), a PR template in the plain-language gitgud-pr style, and optional protection for main via a ruleset (no force push, no deletion, required green checks, review approval opt-in). Every GitHub settings change needs an explicit yes. Use when the user says "set up CI", "add GitHub Actions", "add a workflow", "run tests on PRs", "protect main", "branch protection", "ruleset", "require checks", or "PR template".
---

# CI and branch rules for a repo

Goal: a PR cannot reach `main` with red checks, the checks run what the developer runs locally, and the workflow itself is safe to run on untrusted PRs.

## Rules

- Files in the repo (workflow, PR template) go on a branch and into a PR like any change (`gitgud-branch`, `gitgud-commit`, `gitgud-pr`).
- Every change to GitHub settings needs an explicit yes, one per change, showing the exact command: rulesets, branch protection, secrets, Actions permissions, merge options.
- Least privilege: top-level `permissions: contents: read`; a job gets more only for what it writes. Never use `pull_request_target` together with a checkout of the PR head.
- Pin every third-party action to a full commit SHA with the version as a comment. Never `@main` or a bare tag.
- Never put `claude-code-action`, the Claude CLI or `claude -p` into CI. Review loops run locally (`gitgud-ship-issue`).

## 1. Detect the stack and the real commands

```bash
git ls-files | grep -E '(^|/)(package\.json|pnpm-lock\.yaml|yarn\.lock|pyproject\.toml|requirements.*\.txt|go\.mod|Cargo\.toml|Package\.swift|.*\.xcodeproj|ProjectSettings/ProjectVersion\.txt|Makefile)$'
ls .github/workflows 2>/dev/null       # extend an existing workflow instead of adding a second one
```

Take the commands from the repo (scripts in `package.json`, `Makefile`, `pyproject.toml` tool sections, README), run them locally first, and use only those that pass or that the user wants fixed first. If installing dependencies locally is not allowed, run what you can and list the rest as untested.

| Stack | Setup action | Typical steps |
|---|---|---|
| Node | `actions/setup-node` (`node-version-file: .nvmrc` or `lts/*`, `cache: npm`) | `npm ci` (no lockfile: commit one first, or `npm install` without `cache`), `npm run lint --if-present`, `npm test`, `npm run build --if-present` (pnpm/yarn: their own install) |
| Python | `actions/setup-python` (version from `pyproject.toml`, `cache: pip`) | `pip install -e '.[dev]'` or `-r requirements*.txt`, `ruff check .`, `pytest` |
| Go | `actions/setup-go` (`go-version-file: go.mod`) | `go vet ./...`, `go test ./...`, `go build ./...` |
| Rust | none (rustup is on the runner) | `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test` |
| Swift / Xcode | `runs-on: macos-latest` | `swift test`, or `xcodebuild test -scheme <s> -destination 'platform=iOS Simulator,name=<device>'` |
| Unity | none by default | needs a Unity license as a secret; say so and add a workflow only if the user asks |

Only lint and type-check steps the project already uses. Several languages: one job each.

## 2. Workflow

Look up the SHA of each action's latest release:

```bash
tag=$(gh api repos/actions/checkout/releases/latest --jq .tag_name)
gh api "repos/actions/checkout/commits/$tag" --jq .sha        # full 40-char commit SHA
```

Repeat for every action (`actions/setup-node`, `actions/setup-python` ...).

`.github/workflows/ci.yml` (Node example; swap the steps from the table):

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<sha> # <tag>
        with:
          persist-credentials: false
      - uses: actions/setup-node@<sha> # <tag>
        with:
          node-version: lts/*
          cache: npm
      - run: npm ci
      - run: npm run lint --if-present
      - run: npm test
      - run: npm run build --if-present
```

The job id (`test`) is the check name the ruleset requires. Lint the file locally with `actionlint` if installed (do not install it unasked); otherwise at least parse it: `python3 -c 'import sys,yaml; yaml.safe_load(open(sys.argv[1]))' .github/workflows/ci.yml`. After the PR is open, `gh pr checks --watch` must be green before section 5.

## 3. PR template

`.github/pull_request_template.md` (the body style of `gitgud-pr` section 4 as a fill-in form):

```markdown
**What and why**
<!-- 2-3 sentences an outsider understands. Spell out abbreviations. -->

**Changes**
<!-- At most 5 bullets, one line each. -->
-

**Tested**
- [ ]

**Risks**
<!-- Only real ones. Delete if none. -->

Closes #

<details><summary>Details</summary>

<!-- Run IDs, logs, env vars, paths, design notes. -->
</details>
```

## 4. Commit and open the PR

One PR, `ci: add workflow and PR template` (issue templates from `gitgud-issue` may go in the same PR). Body per `gitgud-pr`, with the list of settings still to change after merge (section 5).

## 5. Protect main (settings change: yes per command)

Check first:

```bash
gh repo view --json visibility,owner -q '.visibility + " " + .owner.login'
gh api repos/{owner}/{repo}/rulesets --jq '.[] | {id, name, enforcement}'
gh api user --jq .plan.name        # own repos only; orgs: gh api orgs/<org> --jq .plan.name. Empty or error: try the POST below, a 403 tells
```

Rulesets and branch protection are free on public repos. On private repos they need a paid plan (Pro, Team or Enterprise); on Free the API answers 403 "Upgrade to GitHub Pro". Then say so and stop; offer to protect main later or make the repo public first (`gitgud-go-public`).

Ruleset for the default branch (`/tmp/ruleset.json`):

```json
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": false,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false}},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": false,
      "required_status_checks": [{"context": "test"}]}}
  ]
}
```

```bash
gh api -X POST repos/{owner}/{repo}/rulesets --input /tmp/ruleset.json
```

- Effect: no force push, no deleting `main`, every change through a PR, merge only with green `test`. List every required job name in `required_status_checks`, and only names that already ran once.
- Required review is opt-in, default off: a solo developer cannot approve their own PR, so `required_approving_review_count: 1` would block every merge. Turn it on only when a second person reviews.
- Change later: `gh api -X PUT repos/{owner}/{repo}/rulesets/<id> --input /tmp/ruleset.json`. Remove: `gh api -X DELETE repos/{owner}/{repo}/rulesets/<id>` (yes needed).
- Classic branch protection only if the repo already uses it; do not set both.

Also offer, with a yes: `gh repo edit --delete-branch-on-merge`.

## Report

List the files added (PR URL), each settings change made and its command, and what was not done (no paid plan, review opt-in left off, commands not run locally).

## Related skills in this pack

`gitgud-pr` (PR body style, checks, merge), `gitgud-issue` (issue templates, `Closes #N`), `gitgud-ship-issue` (local issue -> PR -> review loop that waits for these checks), `gitgud-go-public` (rulesets become free once public).
