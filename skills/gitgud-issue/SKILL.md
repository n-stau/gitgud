---
name: gitgud-issue
description: Write GitHub issues an outsider understands, and run the issue -> branch -> PR flow with the gh CLI - bug and task templates with a plain-language summary first, labels, duplicate check, .github/ISSUE_TEMPLATE forms (bug + task), starting work from an issue with gh issue develop, and closing it from the PR with Closes #N. Turns TODOs, FIXMEs or bugs found while working into issues only after a yes. Use when the user says "open an issue", "create an issue", "file a bug", "write a ticket", "turn this into an issue", "issue template", "make issues from the TODOs", "start work on issue #12", "pick up an issue", or "link the PR to the issue".
---

# Issues people can act on

Goal: anyone can read the first two lines of an issue and know what is wrong or what is wanted, and every issue becomes one branch and one PR that closes it.

## Rules

- Creating an issue the user asked for is fine. These need an explicit yes: creating issues from TODOs, review findings or bugs you noticed; creating or changing labels; editing, closing, reopening or commenting on existing issues; assigning people.
- Search first: `gh issue list --state all --search "<2-3 key words>"`. A match gets a comment (with a yes), not a duplicate. No remote or no network: write the issue as a draft file and say it was not searched or created.
- Issues are public to everyone with repo access: no secrets, tokens, private hostnames, home paths or personal data. Redact logs before pasting.
- Write for an outsider: spell out every abbreviation on first use ("time to live (TTL)"). Run IDs, env vars, file paths and log lines stay out of **Problem** and **Goal**: put them under **Where seen** or inside `<details>` (a command in **Fix** may name a path).
- One issue = one problem or one goal. Two fixes that can ship apart are two issues.

## 1. Bug issue

Title: `<area>: <what goes wrong, in plain words>`.

```markdown
**Problem** <1-2 plain sentences: what goes wrong and why it matters.>
**Where seen** <run, version, command, file or log where it shows up>
**Cause** <what actually causes it, if known; "Unknown" is fine>
**Fix** <the idea, not the full patch>
**Done when**
- [ ] <observable check that proves it is fixed>
```

Worked example:

```markdown
watchdog: log fills with "cannot open loot.jsonl" before first loot

**Problem** Until the agent finds its first loot, every watchdog check writes an error line to the watchdog log. The count itself is right (falls back to 0), but real messages get buried.
**Where seen** Run `20261124_224534`, `watchdog_<ts>.log`.
**Cause** `2>/dev/null` only silences `wc`. The input redirect `< loot.jsonl` fails before that.
**Fix** `{ wc -l < /opt/data/run/loot.jsonl; } 2>/dev/null || echo 0`
**Done when**
- [ ] A fresh run writes no "cannot open" line before the first loot.
```

Anti-example (do not write this): *"wc stderr not suppressed in watchdog loop since redirect binds before 2>/dev/null, see run 20261124_224534 watchdog log, cannot open loot.jsonl spam until first LOOT_EVT, fix by brace-grouping, count OK via fallback."* One dense paragraph mixes problem, cause, evidence and fix; an outsider cannot tell what is wrong or when it is done.

## 2. Task issue

Title: `<area>: <outcome>` (`docs: add install steps for Windows`).

```markdown
**Goal** <one sentence: what is true when this is done.>

**Done when**
- [ ] <check 1>
- [ ] <check 2, at most 5>

<details><summary>Context</summary>

<background, links, constraints, related issues, logs>
</details>
```

More than 5 checks means more than one issue: split it, or make a parent issue whose checklist links the children (`- [ ] #14`).

## 3. Create

```bash
gh label list                                     # reuse existing labels (bug, enhancement, documentation ...)
gh issue create --title "watchdog: log fills with \"cannot open loot.jsonl\" before first loot" \
  --body-file /tmp/issue.md --label bug           # add --assignee @me if the user takes it
```

The title is passed separately, not as the first line of the body file. Missing label, with a yes: `gh label create task --color 0e8a16 --description "Planned work"`. Report the issue URL.

## 4. Issues from TODOs or found bugs (with a yes)

```bash
git grep -nwE 'TODO|FIXME|XXX|HACK' -- ':!*.lock' ':!vendor/' ':!node_modules/'
```

Group hits that belong together, skip those an open issue already covers (reference it in the comment instead), draft one bug or task issue per group (templates above, file and line under **Where seen** or in `<details>`), show the list of titles and wait for a yes. After creating them, offer to replace each comment with `TODO(#N)` in a normal commit.

## 5. Issue -> branch -> PR

```bash
gh issue develop 12 --base main --name fix/12-watchdog-log-noise --checkout   # creates the branch on GitHub, links it to #12
```

Branch name follows `gitgud-branch` (`<type>/<issue>-<short-desc>`). Without `gh issue develop` (older gh, no network): `git switch --no-track -c fix/12-watchdog-log-noise origin/main`. The PR body carries `Closes #12` (`gitgud-pr`); the issue closes when the PR merges into the default branch. `Refs #12` links without closing (partial work).

## 6. Issue templates in the repo

`.github/ISSUE_TEMPLATE/bug.yml`:

```yaml
name: Bug
description: Something does not work as expected
labels: [bug]
body:
  - type: textarea
    id: problem
    attributes: {label: Problem, description: "1-2 plain sentences: what goes wrong and why it matters. Spell out abbreviations."}
    validations: {required: true}
  - type: textarea
    id: where
    attributes: {label: Where seen, description: "Version, command, run ID, log file. Redact secrets and personal data."}
  - type: textarea
    id: cause
    attributes: {label: Cause, description: "If known."}
  - type: textarea
    id: fix
    attributes: {label: Fix, description: "Idea, if any."}
  - type: textarea
    id: done
    attributes: {label: Done when, value: "- [ ] "}
    validations: {required: true}
```

`.github/ISSUE_TEMPLATE/task.yml`:

```yaml
name: Task
description: Planned work with a clear goal
labels: [enhancement]
body:
  - type: input
    id: goal
    attributes: {label: Goal, description: "One sentence: what is true when this is done."}
    validations: {required: true}
  - type: textarea
    id: done
    attributes: {label: Done when, description: "At most 5 checks.", value: "- [ ] "}
    validations: {required: true}
  - type: textarea
    id: context
    attributes: {label: Context, description: "Background, links, logs. Optional."}
```

`.github/ISSUE_TEMPLATE/config.yml`: `blank_issues_enabled: true` (set `false` only if the user wants every issue to use a form). Use labels that exist in the repo. Commit the three files with `gitgud-commit` (`chore: add issue templates`). The PR template lives in `gitgud-ci`.

## Related skills in this pack

`gitgud-branch` (branch naming and updates), `gitgud-pr` (PR body in the same style, `Closes #N`), `gitgud-ci` (PR template, checks and branch rules), `gitgud-ship-issue` (implement an issue end to end with a review loop).
