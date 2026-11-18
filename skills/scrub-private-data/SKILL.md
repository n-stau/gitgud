---
name: scrub-private-data
description: Find and remove private data from a git repo before it goes public or after a leak - secrets (API keys, tokens, passwords, .env, private keys), personal data (names, emails, phone numbers, addresses, home paths, IPs), file metadata (photo EXIF/GPS, PDF and Office authors) and commit metadata (author emails, hostnames, commit messages), in the working tree AND the full history, then rewrite history and purge the old objects. Use when the user wants to publish, clean or check a repo for secrets or personal data, remove a leaked key from git, or strip names, locations, metadata or emails from GitHub.
---

# Scrub private data from a git repo

Goal: nothing private is left in the files, in any commit, in commit or tag messages, in author/committer data, or in file metadata. A secret that was ever pushed counts as leaked: removing it is not enough, it must be rotated.

Tools next to this file (Python stdlib + git, nothing to install):

- `scan.py REPO [--term TEXT ...] [--no-history]`: read-only. Scans current files, every blob in the history, commit and tag messages, author/committer/tagger identities, file metadata and remotes. Secrets are cut in the output.
- `clean.py REPO [options]`: rewrites files and the full history, strips metadata, rewrites identities, then deletes stale refs, expires the reflog and runs `gc --prune=now`. **Default is a dry run** that prints exactly what would change. It only writes with `--apply`, and makes a mirror backup first. It never pushes.
- `meta.py`: metadata reader/stripper used by both (JPEG/PNG/TIFF/HEIC EXIF incl. GPS, PNG text, PDF info + XMP, Office/OpenDocument creator, editor, comment authors).
- `test_scan.py`: end-to-end self-test (plant, scan, dry run, apply, rescan). Run it after changing the scripts.

## Rules

- Scanning is always fine. Changing anything is not: show the dry-run report and get an explicit yes before `--apply`, before a force push, before deleting or recreating a GitHub repo, before making a repo public, and before deleting the backup. One yes covers one step on one repo.
- "Big changes" always need a separate yes even inside an approved cleanup: history rewrite, removing files from history, rewriting identities, `--fresh`, anything that touches more than a handful of files. When the user says "only check" or "nothing to change", run `scan.py` only. Not even a dry run is needed then, unless they ask what a cleanup would do.
- Never print a secret in full: not in chat, commits, logs or tool output.
- Keep values the user wants public (their own name on their own profile, a portfolio link). Ask when unsure.
- Do not install tools. gitleaks, trufflehog, git-filter-repo, exiftool may be suggested with their install command.

## 1. Collect private terms

Patterns cannot know who a name belongs to. Ask the user once and add what you know from context:

- names (own, partner, family, friends, customers) that may sit in test data, fixtures, seeds, comments
- private emails, phone numbers, home address parts (street, postcode, city), workplace/school if private
- device and network names (`Name-MacBook`, `*.fritz.box`, NAS, Tailscale machine names), usernames, account IDs

`git config user.name`, `user.email`, the OS username and every line of `~/.config/scrub-private-data/terms.txt` (personal default terms, kept outside any repo; override the path with `SCRUB_TERMS`) are added automatically. Offer to add new private terms the user names to that file. Names of partners, family or friends in test data are typically only found once they are given as terms.

## 2. Scan (read-only)

```bash
python3 ~/.claude/skills/scrub-private-data/scan.py <repo> --term "Name" --term "Street" ...
```

Each line: `SEVERITY rule path:line [tree | history-only blob <sha> | history | git log] value (+N more in this file)`.

- `history-only blob`: deleted or changed later, still in old commits. Which commits: `git log --all --oneline --find-object=<sha>`.
- `(commit message …)` / `(tag message …)`: private text in a message.
- `commit-identity`: author/committer/tagger emails that are not GitHub noreply. Hostnames like `user@Name-MBP.fritz.box` reveal the device and home network.
- `file-metadata` / `exif-gps`: authors, camera, serial numbers, software, GPS inside photos, PDFs, Office files.

Also look at what the scanner cannot see, and mention it in the report:

- ignored files that get shared another way (`data/`, zips, Docker images, release assets)
- content that tells a story without matching a pattern: setup docs naming the user's server, VPN, folder layout or other private projects
- screenshots showing names or private windows; audio/video tags; blobs over 50 MB
- GitHub-side data: issues, PRs, wiki, releases, Actions logs, Pages, gists
- uncommitted changes in the working copy (they are not scanned as history and block `--apply`)

## 3. Plan with the user (dry run)

Sort findings into: live secret (rotate first), sensitive file, personal data in content, file metadata, commit identity, harmless (test coordinates, example values). Agree on replacements, then:

```bash
python3 ~/.claude/skills/scrub-private-data/clean.py <repo> \
  --replace-file /tmp/reps.txt \
  --remove-path .env --remove-path '*.pem' \
  --strip-metadata \
  --set-identity "n-stau <ID+n-stau@users.noreply.github.com>"
```

`/tmp/reps.txt` holds one `OLD==>NEW` per line, e.g. `John==>Alex`.

Put private values in a replacement file outside the repo, not on the command line. Use `--fresh "Initial public version"` instead when history has no value: one commit, all old commits gone.

Show the user the dry-run report as it is (removed files, replaced text per file, messages, identities, stripped metadata, refs to delete) and ask for the yes.

Code-level fixes (move a secret into an env var, add `.env.example`, extend `.gitignore`) are normal edits. Commit them before `--apply`.

## 4. Apply, purge, verify

After the yes: same command plus `--apply`. It refuses to run with uncommitted changes or a non-empty stash. It makes `<repo>-backup-<time>.git`, rewrites all branches and tags, deletes remote-tracking/stash/notes refs, expires the reflog and runs `gc --prune=now`.

Then rescan with the same terms. The goal is `0 findings`, or only items the user chose to keep. Repeat step 3 for anything left.

## 5. Report everything

Give the user the complete list, not a summary:

- every change from the `CHANGED` report: files removed, each replacement with its files and count, messages changed, identities rewritten, metadata stripped per file, refs deleted, commit count
- secrets that must still be rotated, and by whom
- what the scan cannot see (step 2 list) and what you did not check
- where the backup is

## 6. Push and clean up (each step only with a yes)

- Push rewritten history: `git push --force --all && git push --force --tags`. Other clones and forks still hold the old data.
- Repo never public: deleting and recreating it on GitHub is cleaner than a force push, because old commits otherwise stay reachable by hash.
- Repo was public: rotated secrets are the real fix. GitHub support can purge cached views.
- Delete leftovers once the user confirms the result: the replacement file (`rm /tmp/reps.txt`), temporary clones, and the backup (`rm -rf <repo>-backup-*.git`), which still contains everything.
- For the future: `git config --global user.email ID+user@users.noreply.github.com`, and in GitHub settings enable "Keep my email addresses private" and "Block command line pushes that expose my email".

## Optional: pre-commit guard

```bash
printf '#!/bin/sh\npython3 ~/.claude/skills/scrub-private-data/scan.py . --no-history >&2\n' > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Blocks any commit while findings exist (LOW included), so only add it to repos that already scan clean.
