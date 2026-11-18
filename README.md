<div align="center">

<img src="assets/icon.svg" alt="gitgud icon: a pixel git branch with a crown" width="112" height="112" />

# gitgud

gitgud is a pack of git skills for coding agents that commits, branches, reviews, releases and publishes like a careful maintainer.

![Skills](https://img.shields.io/badge/skills-7-22c55e) ![Claude Code](https://img.shields.io/badge/Claude%20Code-ready-d97757) ![Codex](https://img.shields.io/badge/Codex-ready-111111)

[Installation](#installation) · [Skills](#skills) · [Safety](#safety)

</div>

## Highlights

- **Clean commits**: splits mixed work into logical Conventional Commits, matches the repo's own message style, keeps required trailers.
- **Nothing private slips in**: every commit checks for `.env` files, keys, large binaries and debug leftovers; `scrub-private-data` scans the full history, commit metadata and photo EXIF/GPS.
- **Branches without drama**: rebase or merge chosen by whether the branch is shared, conflict workflow, squash-merge-aware cleanup, reflog recovery.
- **Releases from history**: next semver version and a Keep a Changelog section generated from commits by a stdlib-only script.
- **Ready to open source**: a guided checklist from secret scan to license, README and replacing the old history on GitHub.
- **Asks before it rewrites**: force pushes, history rewrites, deletes and visibility changes always need your explicit yes.

## Installation

```bash
git clone https://github.com/n-stau/gitgud.git
cd gitgud
./install.sh
```

The script symlinks every skill into `~/.claude/skills` and `~/.agents/skills`. Requires git 2.40+, Python 3.9+ and, for pull requests and releases, the [GitHub CLI](https://cli.github.com).

## Quick start

Skills load on their own when a request matches. Just ask:

```text
commit my work
clean up my merged branches
open a PR for this
cut a release
make this repo ready to go public
```

## Skills

| Skill | Purpose |
|---|---|
| `gitgud-commit` | Logical commits with Conventional Commits messages and a pre-commit safety check |
| `gitgud-branch` | Naming, staying up to date, conflicts, worktrees, cleanup and recovery |
| `gitgud-pr` | Self-review, PR title and body, splitting, review replies, merge and cleanup |
| `gitgud-release` | Semver bump, changelog, manifest versions, annotated tag and GitHub release |
| `gitgud-go-public` | Release-readiness checklist for publishing a private repo |
| `scrub-private-data` | Find and remove secrets, personal data and metadata in files and full history |
| `write-readme` | READMEs in the style of big-company open-source repos |

## Safety

- Read-only by default: scans and dry runs never change the repo.
- One yes per destructive step: force push, history rewrite, branch or repo deletion, tag push, release, visibility change.
- Backups before rewrites, secrets never printed in full, nothing pushed unless you ask.

## License

[MIT](LICENSE) © n-stau
