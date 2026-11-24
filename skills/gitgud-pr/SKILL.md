---
name: gitgud-pr
description: Take a branch from finished work to merged PR with the gh CLI - clean up history, self-review the full diff against the base, run tests and lint, write the title and a plain-language body (what and why, changes, tested, risks, Closes #N, details collapsed), keep PRs small or split them, choose draft vs ready, watch checks, answer review comments, merge with the strategy the repo allows, and clean up afterwards. Use when the user says "open a PR", "create a pull request", "make a PR", "is this ready for review", "address review comments", "reply to the review", "check CI on my PR", "merge the PR", "squash and merge", or "clean up after merge".
---

# Pull requests from ready to merged

Goal: a reviewer understands the PR from its title and first paragraph, can review the diff in one sitting, and nothing surprising lands on the default branch.

## Rules

- Check for an existing PR for the branch before creating one: `gh pr view --json number,url,state` (fails when there is none).
- Opening a PR the user asked for is fine. These need an explicit yes: merging, closing, `--admin` merges, force pushes, posting comments or review replies the user did not ask you to write, requesting reviewers, deleting branches.
- Never merge with failing required checks or unresolved requested changes.
- Title, body and comments are public to everyone with repo access: no secrets, private paths, internal hostnames or personal data.
- Add an attribution line only if the user or environment requires one; then put it at the end of the body.

## 1. Prepare the branch

```bash
gh repo view --json defaultBranchRef -q .defaultBranchRef.name    # base branch; offline: git symbolic-ref --short refs/remotes/origin/HEAD
git fetch origin
git log --oneline --reverse origin/main..HEAD     # commits that will be in the PR
git rebase origin/main                            # private branch; shared branch: git merge --no-edit origin/main
```

Use that base branch wherever this skill says `main`.

- Fold wip, typo and fixup commits into the commit they belong to before review (ask first; see `gitgud-commit`). Non-interactive: for new fixes `git commit --fixup <sha>`, then `GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash origin/main`. Existing `wip`/`fix typo` commits fold into the commit before them with `GIT_SEQUENCE_EDITOR='sed -i.bak -E "s/^pick ([0-9a-f]+ (# )?(wip|WIP|fix typo)([: ]|$))/fixup \1/"' git rebase -i origin/main` (handles both `pick <sha> <subject>` and git >= 2.45 `pick <sha> # <subject>`; check `git log` afterwards). After review started, add new commits instead of rewriting, unless the repo asks for rebased PRs.
- Run what CI runs: read `.github/workflows/*.yml` (or the repo's CI config) and run the same test, lint, type-check and build commands locally. Report anything you could not run.

## 2. Self-review the full diff

```bash
git diff --stat origin/main...HEAD
git diff origin/main...HEAD
git diff origin/main...HEAD | grep -nE '^\+.*(console\.log|print\(|debugger|breakpoint\(\)|binding\.pry|dbg!|TODO|FIXME|XXX)'
```

Read every hunk as the reviewer would. Look for: changes unrelated to the goal, debug output, commented-out code, missing tests for new behavior, secrets or `.env` files, generated files, lockfile churn, docs or changelog that should change with the code.

Then: remove debug output (ask if unsure whether it is intended logging), turn TODOs into follow-ups listed in the PR body, and check that new tests are actually picked up by the test command (they show in its output or count).

## 3. Size and split

- Aim for under ~400 changed lines (excluding generated files and lockfiles) and one concern. `git diff --shortstat origin/main...HEAD` tells you.
- Split when a part can be reviewed or reverted on its own: mechanical refactor or rename first, then the behavior change; dependency bump separate; formatting never mixed with logic.
- Ask before turning one requested PR into several. Independent slices go into separate PRs off the default branch: `git switch -c <slice> origin/main && git checkout <branch> -- <paths> && git commit`. Stack (`gh pr create --base <previous-branch>`) only when one really needs the other, and say so in the body.

## 4. Title and body

Title: what changes for the user, in the repo's style. If PRs are squash-merged, the title becomes the commit subject, so use the commit convention (`feat(auth): add OAuth login`). Look at `gh pr list --state merged --limit 10`.

Body: use the repo's template if one exists (`git ls-files | grep -i pull_request_template`) and fill it in this style. Otherwise:

```markdown
**What and why** <2-3 sentences an outsider understands: the problem and what this PR does about it.>

**Changes**
- <at most 5 bullets, one line each, what a reviewer must know; not a file list>

**Tested**
- [x] <command run or manual step, with result>
- [ ] <check that could not run, and why>

**Risks** <only real ones: migrations, config or behavior changes, rollback. Leave the section out if none.>

Closes #123

<details><summary>Details</summary>

<run IDs, logs, env vars, paths, design notes, follow-ups>
</details>
```

- Spell out every abbreviation on first use. Run IDs, env vars and paths go only into `<details>`, never into "What and why".
- No wall of insider jargon: if a sentence needs the codebase to make sense, rewrite it or move it into `<details>`.
- No issue: leave out `Closes`. Partial work: `Refs #N`.
- More than ~400 changed lines: split first (section 3) instead of writing a longer body.

Add screenshots or a short recording for UI changes (drag into the PR on GitHub; gh cannot upload images). `Closes #N` / `Fixes #N` closes the issue on merge; `Refs #N` only links.

## 5. Create

```bash
git push -u origin HEAD
gh pr create --base main --title "feat(auth): add OAuth login" --body-file /tmp/pr-body.md
gh pr view --json url,isDraft,mergeStateStatus
```

- Ready by default, so CI and review bots run. `--draft` only when the user wants early feedback on unfinished work; flip later with `gh pr ready`.
- Optional: `--assignee @me`, `--label <name>`, `--reviewer <login>` (requesting reviewers notifies people: needs a yes unless asked).
- If `gh pr create` fails on a GraphQL rate limit: `gh api repos/{owner}/{repo}/pulls -f title=... -f head=<branch> -f base=main -F body=@/tmp/pr-body.md`.

## 6. Checks and review

```bash
gh pr checks --watch --fail-fast          # exits non-zero if a check fails
gh pr view --comments                     # conversation and review summaries
gh api 'repos/{owner}/{repo}/pulls/<N>/comments?per_page=100' --jq '.[] | {id, path, line, user: .user.login, body}'
gh api graphql -F o=<owner> -F r=<repo> -F n=<N> -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved path line comments(first:10){nodes{databaseId author{login} body}}}}}}}' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not)'
```

For each unresolved comment: fix it in a new commit, or explain why not. A nit can be declined with a reason; a question gets an answer (plus a code comment if that helps the next reader). Push first, then reply in the thread, short and concrete (what changed, which commit; the SHA must exist on GitHub). Draft the replies and show them to the user before posting, unless the user said to post. Inline reply: `gh api -X POST 'repos/{owner}/{repo}/pulls/<N>/comments/<comment-id>/replies' -f body='Fixed in abc1234.'`; top-level review comment: `gh pr comment <N> --body '...'`. Leave resolving threads to the reviewer unless the user or repo says otherwise. A failing check: read the log (`gh run view <run-id> --log-failed`), reproduce locally, fix; do not re-run until it passes by luck.

## 7. Merge (with a yes)

```bash
gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed,viewerDefaultMergeMethod,deleteBranchOnMerge
gh pr view --json reviewDecision,mergeStateStatus,statusCheckRollup
```

Use the method the repo allows and its history shows. Without a convention: `--squash` for a feature branch with messy commits, `--rebase` for a branch of clean, individually meaningful commits, `--merge` when the branch history itself matters (release branches, long-lived integration). Then:

```bash
gh pr merge <N> --squash --delete-branch      # or --rebase / --merge; --auto waits for required checks
```

## 8. After merge

```bash
git switch main && git pull --ff-only
git fetch --prune origin
git branch -d <branch>      # a squash or rebase merge needs -D; confirm first: gh pr view <N> --json state -q .state  -> MERGED
```

Report the PR URL, merge method, and anything left open (follow-up issues, unresolved comments).

## Related skills in this pack

`gitgud-commit` (clean commits before review), `gitgud-issue` (issues in the same style, issue -> branch), `gitgud-ci` (checks and rules for main), `gitgud-ship-issue` (issue -> PR -> review loop), `gitgud-branch` (rebase, conflicts, branch cleanup), `gitgud-release` (ship what was merged), `gitgud-go-public` (publish a private repo).
