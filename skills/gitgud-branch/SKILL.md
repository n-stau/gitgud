---
name: gitgud-branch
description: Create, update and clean up git branches safely - branch naming (type/short-desc with ticket ids), branching off the fetched default branch, rebase vs merge to stay up to date, conflict resolution, stash vs WIP commit, worktrees for parallel work, deleting merged or squash-merged branches locally and on the remote (dry-run list first), and recovering lost commits or branches via reflog. Use when the user says "new branch", "create a branch", "start work on", "update my branch", "rebase on main", "sync with main", "merge conflict", "resolve conflicts", "stash", "worktree", "clean up branches", "delete merged branches", "I lost my commits", "undo reset", or "recover branch".
---

# Branch without losing work

Goal: every piece of work lives on its own well-named branch cut from an up-to-date base, stays current without surprising collaborators, and nothing is ever lost on the way.

## Rules

- Always `git fetch` before branching, rebasing or comparing with the remote.
- Never commit directly to the default branch (`main`, `master`, `develop`, `trunk`) of a repo that uses PRs, and never push to it. Branch first.
- These need an explicit yes, one per action, naming the branch: force push (always `--force-with-lease`, never plain `--force`), `git branch -D`, deleting remote branches, rebasing a branch others have pulled, `git reset --hard`, `git clean`, dropping a stash.
- Before any risky rewrite, leave a safety ref: `git branch backup/<name>-$(date +%s)`. Delete backups only when the user says so.
- Run git non-interactively: `GIT_EDITOR=true` for `--continue`, `--no-edit` for merges. Never leave a rebase or merge half-done; finish it or `--abort`.

## 1. Name and create the branch

- Format: `<type>/<ticket>-<short-desc>` (ticket only if one exists), lowercase, hyphens, 2-5 words: `feat/123-oauth-login`, `fix/JIRA-88-null-token`, `feat/login-rate-limit`. Types match commit types (`feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`). Follow the repo's pattern if `git branch -r` shows another one (e.g. `user/topic`).
- Find the default branch and create from its fetched tip:

  ```bash
  git fetch --prune origin
  git symbolic-ref --short refs/remotes/origin/HEAD     # e.g. origin/main; if missing: git remote set-head origin --auto
  git status --porcelain                                # uncommitted changes? see below
  git switch --no-track -c feat/123-oauth-login origin/main
  git push -u origin HEAD                               # first push sets the upstream to the same name
  ```

  Use the default branch the second command printed wherever this skill says `origin/main`.

  Dirty tree: ask whether the changes belong on the new branch. If yes, `switch` carries them along (it refuses when they conflict: then stash, switch, `git stash pop`). If no, `git stash push -u -m "<what>"` first. A `stash pop` that conflicts keeps the stash entry: resolve, `git add`, then `git stash drop` only with a yes.

  `--no-track` keeps the new branch from tracking `origin/main`, so `git push` cannot target the default branch by accident. Branch off something else (a release branch, a stacked PR) only when the user or the task says so.

## 2. Stay up to date

```bash
git fetch origin
git log --oneline HEAD..origin/main      # what is new on the base
```

- Shared or private? `git log --format='%ae' origin/main..@{u} | sort -u` lists who committed on the remote branch; anyone besides you, an open review, or a repo that forbids force pushes means shared.
- Private branch (only you push to it, PR not yet reviewed): `git rebase origin/main`. If already pushed, the push needs `git push --force-with-lease`, which needs a yes. After a rebase never run `git pull` to "fix" the rejected push: it merges the old commits back in.
- Shared branch: first take your teammates' commits, then main, then a normal push:
  `git merge --ff-only @{u} || git merge --no-edit @{u}`, `git merge --no-edit origin/main`, `git push`.
- Never rebase the default branch or a release branch.

## 3. Resolve conflicts

1. See what conflicts: `git status --short` (`UU` lines) or `git diff --name-only --diff-filter=U`.
2. Read both sides and the intent of each commit (`git log -1 <sha>`, the PR). During a **rebase** `--ours` is the base you rebase onto and `--theirs` is your commit; during a **merge** it is the other way round. Take a whole side only when that is clearly right: `git checkout --theirs -- <file>`.
3. Edit to the combined result, then check no markers are left: `git grep -nE '^(<<<<<<<|=======|>>>>>>>)( |$)' -- <files>` prints nothing.
4. Run the tests touching those files.
5. `git add -- <files>`, then `GIT_EDITOR=true git rebase --continue` or `GIT_EDITOR=true git merge --continue`.
6. Unsure about a conflict's intent: ask the user instead of guessing. To back out completely: `git rebase --abort` / `git merge --abort`.

## 4. Park work: stash or WIP commit

- Short interruption, same branch soon: `git stash push -u -m "wip: login form"`, later `git stash list` and `git stash pop` (`apply` keeps the entry). `-u` includes untracked files.
- Longer, or switching machines, or more than one parked item: a WIP commit on the feature branch, `git add -- <paths> && git commit -m "wip: login form"`, undone later with `git reset --soft HEAD~1`. Do not push WIP commits to shared branches.

## 5. Parallel work with worktrees

Use a worktree instead of stashing when two branches must be open at once (a hotfix during a feature, an agent working in parallel):

```bash
git worktree add --no-track -b fix/7-crash ../repo-fix-7 origin/main
git worktree list
git worktree remove ../repo-fix-7 && git worktree prune     # removing the worktree keeps the branch
```

A branch can be checked out in one worktree only (`+` in `git branch` marks the others). A new worktree has no untracked files: install dependencies and copy local config (`.env`) before running tests there.

## 6. Clean up merged branches (dry run first)

```bash
git fetch --prune origin
# local branches merged into the base, skipping the current one and those checked out in worktrees
git for-each-ref --merged origin/main --format='%(refname:short) %(worktreepath)' refs/heads | awk '$2=="" {print $1}' | grep -vxE 'main|master|develop|trunk'
# local branches whose changes are already in the base (finds squash merges: merging them would change nothing)
base_tree=$(git rev-parse 'origin/main^{tree}')
for b in $(git for-each-ref --format='%(refname:short)' refs/heads); do
  [ "$(git merge-tree --write-tree origin/main "$b" 2>/dev/null | head -1)" = "$base_tree" ] && echo "$b"
done | grep -vxE 'main|master|develop|trunk'   # also lists brand-new branches with no commits yet: skip those
# local branches whose remote branch was deleted: merged OR abandoned, check each one
git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads | awk '$2=="[gone]" {print $1}'
# remote branches merged into the base
git branch -r --merged origin/main --format='%(refname:lstrip=3)' | grep -vxE 'HEAD|main|master|develop|trunk'
```

Show the lists, then after a yes:

- Merged: `git branch -d <names>`. Only delete what the first list showed: `-d` also accepts a branch merged into its own upstream but not into main.
- Squash-merged (second list): `-d` refuses them; `git branch -D <branch>` with a yes. Do not use `git cherry` for this: a multi-commit squash shows `+` lines although it is merged.
- Gone (third list) but in neither of the first two: probably abandoned or unfinished. Check `gh pr list --head <branch> --state all` and show `git log --oneline origin/main..<branch>` before asking.
- Remote: `git push origin --delete <name>` with a yes per branch list; try `git push --dry-run origin --delete <name>` first.

## 7. Recover lost work

- `git reflog -20` shows every position HEAD had. Restore a branch tip with `git branch rescue/<name> <sha>` (safe), or, with a yes, move back with `git reset --hard 'HEAD@{1}'` (uncommitted changes are lost; stash them first).
- Deleted branch: `git branch -d/-D` prints `(was <sha>)`; `git branch <name> <sha>`. If that output is gone: in `git reflog`, find `checkout: moving from <name> to ...`; that entry's sha is the branch tip.
- Dropped stash or orphaned commit: `git fsck --unreachable --no-reflogs | awk '/commit/ {print $3}' | xargs -r git log --no-walk --format='%h %s'`, then `git stash apply <sha>` or `git branch rescue <sha>`.
- Mid-rebase mess: `git rebase --abort` returns to the starting point; after a finished bad rebase, `ORIG_HEAD` or the reflog entry before `rebase (start)` holds the old tip.

## Related skills in this pack

`gitgud-commit` (what goes into each commit), `gitgud-pr` (open, review and land the branch), `gitgud-release` (tag and release from the default branch), `gitgud-go-public` (publish a private repo).
