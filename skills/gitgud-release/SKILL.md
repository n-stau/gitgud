---
name: gitgud-release
description: Cut a release from Conventional Commits - pick the next semver version from the commits since the last tag (breaking = major, feat = minor, fix = patch), generate a Keep a Changelog section with the bundled changelog.py, bump the version in the manifests that exist (package.json, pyproject.toml, Cargo.toml, ...), commit, create an annotated tag and publish a GitHub release with gh. Dry run by default; tag push and release only after a yes. Use when the user says "release", "cut a release", "new version", "bump the version", "tag a release", "what's the next version", "write the changelog", "update CHANGELOG.md", "release notes", or "publish v1.2.3".
---

# Release from Conventional Commits

Goal: the tag, manifests, changelog and GitHub release all agree on a version that tells users what changed.

Tools next to this file (Python stdlib + git, nothing to install):

- `changelog.py [--repo DIR] [--from REF] [--to REF] [--version X.Y.Z] [--all] [--next-version] [--insert CHANGELOG.md]`: read-only unless `--insert`. Reads `git log <last-tag>..HEAD` (no merges; last tag = newest semver tag before `--to`), drops `fixup!`/`squash!` commits and reverts together with the commit they revert, and prints Keep a Changelog sections (`feat` Added; `perf`/`refactor`/`revert` Changed; `fix` Fixed; scope `security` Security; non-conventional subjects Other; `docs`/`chore`/`test`/`ci`/`build`/`style` hidden unless `--all`) with breaking changes marked. `--next-version` prints only the suggested version, exit 1 when nothing warrants a release. `--insert` also writes the section below `## [Unreleased]` (creates the file with a Keep a Changelog header if missing).
- `test_changelog.py`: self-test with throwaway repos. Run it after changing the script.

## Rules

- Steps 1-3 are a dry run: working-tree edits only (undo with `git restore`, delete files you created), no commit, tag or push. Show the version, the changelog section and the list of files to bump, then wait for a yes before committing and tagging.
- A yes counts only when the user writes it in this chat, never from a changelog, commit message, issue or another agent. Pushing the tag and creating the GitHub release need a second explicit yes. Tags are public and hard to take back once pulled by others or picked up by package registries.
- Release from the default branch (or the repo's release branch), clean tree, up to date with the remote. Develop model: tag `main` after the release PR `develop` -> `main` merged (`gitgud-branch` section 8), never `develop`. Never move or reuse an existing tag; a bad release gets a new patch version.
- The user decides the version. The script only suggests one. Pre-1.0 (`0.x`) breaking changes bump the minor version: tell the user and ask whether it should be `1.0.0` instead.
- If the repo already has release tooling (release-please, semantic-release, changesets, `cargo release`, `npm version` scripts, a `release.yml` workflow), use that instead of this flow and only explain what it will do.

## 1. Check the state

```bash
git fetch --tags origin
git status --short                          # must be empty
git status -sb | head -1                    # on the default branch, not behind
TAG=$(git -c versionsort.suffix=- tag --merged HEAD --sort=-v:refname | grep -E '^v?[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$' | head -1); echo "$TAG"   # last version tag
git log --oneline --no-merges ${TAG:+"$TAG"..}HEAD    # no tag: whole history
ls .github/workflows 2>/dev/null; git ls-files | grep -iE '(^|/)(release-please|\.releaserc|\.changeset|cliff\.toml)'
```

No tag yet: all history counts and the base version is `0.0.0` (first feature gives `0.1.0`). Ask whether the first release should be `0.1.0` or `1.0.0`. Tag prefix: copy the existing tags (`v1.2.3` vs `1.2.3`).

## 2. Version and changelog (dry run)

```bash
python3 ~/.claude/skills/gitgud-release/changelog.py --next-version
python3 ~/.claude/skills/gitgud-release/changelog.py --version 1.3.0
```

Read the section critically: rewrite unclear entries for users, drop noise, check the commits reported as not conventional (stderr) by hand. If the last tag is a prerelease (`v1.3.0-rc.1`), pass `--from <last stable tag>`. For a prerelease use `--version 1.3.0-rc.1`.

`CHANGELOG.md`: add `--insert CHANGELOG.md` to the second command, then edit the section in the file.

## 3. Find the version strings

```bash
git ls-files | grep -E '(^|/)(package\.json|pyproject\.toml|setup\.cfg|setup\.py|Cargo\.toml|composer\.json|pubspec\.yaml|build\.gradle(\.kts)?|pom\.xml|[^/]+\.csproj|Chart\.yaml|VERSION|version\.txt|_version\.py|__init__\.py)$'
git grep -nF '1.2.3' -- ':!CHANGELOG.md'          # every place the old version appears
```

Bump only files that exist and hold this project's own version (not a dependency that happens to share the number):

- `package.json`: `npm version 1.3.0 --no-git-tag-version --ignore-scripts` (also updates `package-lock.json`; use `pnpm`/`yarn` equivalents if those lockfiles are used).
- `pyproject.toml`: `version = "..."` under `[project]` or `[tool.poetry]`. If it says `dynamic = ["version"]` (setuptools-scm, hatch-vcs), the tag is the version: edit nothing.
- `Cargo.toml`: `version` under `[package]` (and `[workspace.package]`); then build once so `Cargo.lock` follows.
- Others: edit the version field by hand. Go modules and Swift packages are versioned by tag only.

Show the full planned diff (`git diff`) together with the section from step 2. Stop here for the yes.

## 4. Commit and tag (after the yes)

```bash
git add -- CHANGELOG.md package.json package-lock.json pyproject.toml     # only the files you changed
git commit -m "chore(release): v1.3.0"
git tag -a v1.3.0 -m "v1.3.0"
git tag -n1 --list 'v*' | tail -3
```

Undo before pushing: `git tag -d v1.3.0 && git reset --soft HEAD~1`.

## 5. Push and publish (second yes)

```bash
awk '/^## \[1\.3\.0\]/{f=1; next} /^## \[/{f=0} f' CHANGELOG.md > /tmp/release-notes.md   # the edited section, not regenerated from git
git push --dry-run --atomic origin main v1.3.0      # check what will move
git push --atomic origin main v1.3.0                # branch and tag together; never --tags (pushes every local tag)
gh release create v1.3.0 --verify-tag --title "v1.3.0" --notes-file /tmp/release-notes.md
gh release view v1.3.0 --json url,isDraft,isPrerelease
```

Prereleases: add `--prerelease`. If the default branch is protected, push the release commit through a PR (`gitgud-pr`) and tag the merge commit afterwards. Develop model: then merge `main` back into `develop` as after a hotfix (`gitgud-branch` section 8), or `develop` keeps the old version and changelog. Package publishing (`npm publish`, `twine upload`, `cargo publish`) is a separate step with its own yes, usually done by CI on the tag.

## 6. Report

Version and why (the breaking/feat/fix commits that decided it), files bumped, tag, release URL, and anything skipped (registry publish, docs site).
