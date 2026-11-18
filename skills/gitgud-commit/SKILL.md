---
name: gitgud-commit
description: Decide what to commit and how - inspect the diff, split it into small logical commits (path or hunk staging without interactive mode), write Conventional Commits messages that match the repo's own history, check staged files for secrets, .env, build output and large binaries, and handle amend/fixup safely. Use when the user says "commit", "commit this", "commit my changes", "make a commit", "split into commits", "clean up commits", "fixup", "amend", or asks for a commit message for staged work.
---

# Commit like a careful maintainer

Goal: each commit is one logical change that builds on its own, has a message a reviewer understands without the diff, and contains nothing private or generated.

## Rules

- Repo conventions beat these defaults. Read `git log` before writing the first message.
- Stage by name: `git add -- <paths>` or hunk patches. Never `git add .` / `git add -A` on a tree you have not fully read.
- Never commit secrets, `.env` files, keys, build output, dependency folders or large binaries. If one is staged, unstage it and tell the user.
- Never use `--no-verify` to get past a failing hook. Fix the cause or ask.
- Amend, fixup and rebase only commits that are not pushed. Rewriting pushed history on a shared branch needs an explicit yes, and the force push needs its own yes.
- Keep every trailer the user or environment requires (e.g. `Co-Authored-By:`, `Signed-off-by:`). A trailer the user asks for "always" applies to every commit in the session. Add no other attribution.
- Do not commit when the user only asked for a message. Do not push unless asked.

## 1. Read the state

```bash
git status --short -uall # -uall lists files inside new folders
git diff                 # unstaged (does NOT show untracked files: read every new file before staging it)
git diff --cached        # already staged: respect what the user staged on purpose
git log --oneline -20
git log -200 --format=%s | sed -nE 's/^([a-z]+)(\([^)]*\))?!?:.*/\1/p' | sort | uniq -c | sort -rn   # types in use
git log -200 --format=%s | sed -nE 's/^[a-z]+\(([^)]+)\)!?:.*/\1/p' | sort | uniq -c | sort -rn     # scopes in use
```

Empty output from both counters means the repo does not use Conventional Commits: then copy its style (capitalization, tense, ticket prefix like `ABC-123:`) instead.

## 2. Group into logical commits

One commit = one reason to change: a feature with its tests, a fix with its regression test, a rename, a dependency bump, a formatting pass. Split when a reviewer would want to revert one part without the other. Do not split a change so that an intermediate commit breaks the build.

- Whole files: `git add -- src/parser.py tests/test_parser.py`
- Part of a file (non-interactive `git add -p`):

  ```bash
  git diff -U0 -- calc.py > /tmp/all.patch                      # -U0: changes 1-2 lines apart stay separate hunks
  awk '/^@@/{n++} n!=2' /tmp/all.patch > /tmp/hunks.patch        # drop hunk 2 (repeat for others; keep the header)
  git apply --cached --unidiff-zero --check /tmp/hunks.patch && git apply --cached --unidiff-zero /tmp/hunks.patch
  ```

  Remove whole `@@ ... @@` blocks only; editing lines inside a hunk breaks its line counts (add `--recount` if you must). Then stage the rest normally for the next commit.
- Check before each commit: `git diff --cached --stat` and `git diff --cached --check` (whitespace errors, conflict markers).

## 3. Pre-commit safety check

```bash
git ls-files --cached --ignored --exclude-standard     # tracked/staged files that .gitignore says should not be
git diff --cached --name-only | grep -iE '(^|/)(\.env(\.[^/]*)?|.*\.(pem|key|p12|pfx|keystore|jks)|id_(rsa|ecdsa|ed25519)|\.npmrc|\.pypirc|credentials(\.json)?)$' | grep -vE '\.(example|sample|template)$'
git diff --cached --name-only --diff-filter=AM -z | xargs -0 -r du -k | awk -F'\t' '$1 > 1024 {print $2 " (" $1 " KB)"}'    # files over 1 MB
git diff --cached -U0 | grep -nE '^\+.*(console\.log|debugger;|breakpoint\(\)|print\(["'"'"']DEBUG|binding\.pry|var_dump\(|TODO|FIXME)'   # leftovers
git diff --cached --name-only --diff-filter=AM -z | xargs -0 -r git grep --cached -liIE '(AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|sk-[A-Za-z0-9_-]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|(api[_-]?key|secret|passw(or)?d|token)[[:space:]]*[:=][[:space:]]*.{0,2}[A-Za-z0-9/+_-]{16,})' --
```

All five print nothing when clean. The secret grep lists file names only; open a hit and judge it without echoing the value. Leftover hits (debug output, TODOs): show them and ask before removing or committing them. Fix for a sensitive file: `git restore --staged -- <file>`, offer to add it to `.gitignore` (ask first; separate `chore:` commit), move the value to an env var with a committed `.env.example`. Large binaries belong in Git LFS or a release asset: ask. A deeper scan (history, personal data, metadata) is the `scrub-private-data` skill, if installed: `python3 ~/.claude/skills/scrub-private-data/scan.py . --no-history`.

## 4. Write the message

```
<type>(<scope>)!: <imperative summary, no period>

<body: why, not what - wrapped at 72>

BREAKING CHANGE: <what breaks and how to migrate>
Closes: #42
Co-Authored-By: Name <email>
```

The footer is the last paragraph and every line in it is `Key: value` (one line without a colon and git sees no trailers at all). Check with `git log -1 --format=%B | git interpret-trailers --parse`.

- Types: `feat` (new behavior), `fix` (bug), `perf`, `refactor` (no behavior change), `docs`, `test`, `build` (build system, deps), `ci`, `chore` (tooling, housekeeping), `style` (formatting only), `revert`.
- Subject: imperative ("add", not "added"), at most 72 characters (aim for 50), lowercase after the colon unless the repo capitalizes. Scope only from scopes the repo already uses, or the obvious module name; omit when unclear.
- Body only when the why is not obvious: the problem, the constraint, the rejected alternative. No file inventory, no "this commit".
- Breaking change: `!` after type/scope and a `BREAKING CHANGE:` footer with the migration path.
- Multi-line messages through stdin, never an editor:

  ```bash
  git commit -F - <<'EOF'
  fix(parser): keep trailing newline in heredocs

  Stripping it changed the hash of every cached template.

  Co-Authored-By: Name <email>
  EOF
  ```

  One-liners: `git commit -m "docs: fix install command" --trailer "Co-Authored-By: Name <email>"`.

## 5. Amend and fixup

First check whether the target is pushed: `git fetch`, then `git branch -r --contains <sha>` prints nothing for a commit that is only local. (`git log --oneline @{upstream}..HEAD` lists unpushed commits too, but fails with "no upstream configured" on a branch that was never pushed: then it is local.)

- Last commit, not pushed: `git commit --amend --no-edit` (content) or `git commit --amend -m "..."` (message).
- Older commit, not pushed: `git commit --fixup=<sha>`, then `GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <base>` (the env var accepts the todo list unchanged, no editor opens). On conflict: resolve, `git add`, `GIT_EDITOR=true git rebase --continue`, or `git rebase --abort` to get back.
- Pushed commit: make a new commit instead. Rewrite only with an explicit yes, then `git push --force-with-lease`.
- Undo the last local commit but keep the changes: `git reset --soft HEAD~1`.

## 6. Report

List the commits made (`git log --oneline <before>..HEAD`), anything left unstaged on purpose, and anything you refused to commit and why.

## Related skills in this pack

`gitgud-branch` (branches, rebase, conflicts, recovery), `gitgud-pr` (open and land the PR), `gitgud-release` (changelog and tags from these commit messages), `gitgud-go-public` (publish a private repo).
