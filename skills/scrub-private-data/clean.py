#!/usr/bin/env python3
"""Remove private data from a git repo's files AND full history, then purge the old objects.

Default is a DRY RUN: it prints exactly what would change and writes nothing. Add --apply to do it.
Stdlib + git only (no git-filter-repo). Every branch and tag is rewritten via fast-export/fast-import.

  clean.py REPO [--replace OLD==>NEW ...] [--replace-file FILE] [--remove-path GLOB ...]
                [--strip-metadata] [--set-identity "Name <email>"] [--fresh "message"] [--apply] [--no-backup]

--replace         literal text replaced in text files, commit/tag messages and author/committer names+emails
--replace-file    one OLD==>NEW per line (keeps private values out of shell history)
--remove-path     fnmatch glob removed from every commit (".env", "*.pem", "secrets/*")
--strip-metadata  remove EXIF/GPS, PNG text, PDF author/creator, Office creator/editor/comment authors
--set-identity    every author/committer/tagger becomes this identity
--fresh           replace the whole history with one commit of the cleaned current tree
After --apply: refs other than branches/tags (remotes, stash, notes) are deleted, reflog expired, gc --prune=now.
Pushing is never done here.
"""
import argparse, collections, fnmatch, os, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta
from scan import RULES, redact


def shown(o):
    """Personal values are printed in full so the user sees what changed; secret-looking ones are cut."""
    if any(sev == "HIGH" and rx.search(o) for _, sev, rx in RULES):
        return redact("x", o)
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.\w+", o):
        return o
    token_like = not re.search(r"\s", o) and len(o) >= 8 and re.search(r"[A-Za-z]", o) and re.search(r"\d", o)
    return redact("x", o) if token_like else o


def git(repo, *a, data=None, env=None):
    r = subprocess.run(["git", "-C", repo, *a], input=data, capture_output=True, env=env)
    if r.returncode:
        sys.exit(f"git {' '.join(a[:2])} failed: {r.stderr.decode().strip()}")
    return r.stdout


def unquote(p):
    if not p.startswith(b'"'):
        return p.decode("utf-8", "replace")
    return p[1:-1].decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")


class Report:
    def __init__(self):
        self.text = collections.Counter()      # (old, new) -> occurrences in files
        self.text_files = collections.defaultdict(set)
        self.messages = collections.Counter()  # (old, new) -> occurrences in commit/tag messages
        self.removed = collections.defaultdict(int)  # path -> commits whose tree contains it (see count_removed)
        self.idents = collections.Counter()    # (old, new) -> commits
        self.meta = collections.defaultdict(set)  # path -> fields stripped

    def show(self, applied):
        head = "CHANGED" if applied else "DRY RUN - would change (nothing written)"
        print(f"\n===== {head} =====")
        sec = lambda t: print(f"\n## {t}")
        sec("Removed files (from every commit)")
        for p, n in sorted(self.removed.items()): print(f"  - {p}  ({n} commits)")
        sec("Replaced text in files")
        for (o, n), c in self.text.most_common():
            files = sorted(self.text_files[(o, n)])
            print(f"  - '{shown(o)}' -> '{n}'  {c}x in {len(files)} file(s): {', '.join(files[:8])}{' …' if len(files) > 8 else ''}")
        sec("Replaced text in commit/tag messages")
        for (o, n), c in self.messages.most_common(): print(f"  - '{shown(o)}' -> '{n}'  {c}x")
        sec("Rewritten identities (author/committer/tagger)")
        for (o, n), c in self.idents.most_common(): print(f"  - {o}  ->  {n}  ({c} lines)")
        sec("Stripped metadata")
        for p, f in sorted(self.meta.items()): print(f"  - {p}: {', '.join(sorted(f))}")
        if not any((self.removed, self.text, self.messages, self.idents, self.meta)):
            print("\n(nothing matched)")


def subst(body, reps, rep, where, path=None):
    for old, new in reps:
        c = body.count(old)
        if c:
            key = (old.decode("utf-8", "replace"), new.decode("utf-8", "replace"))
            (rep.text if where == "file" else rep.messages)[key] += c
            if path: rep.text_files[key].add(path)
            body = body.replace(old, new)
    return body


def rewrite(stream, reps, removes, ident, strip_meta, rep):
    """Edit a fast-export stream. Blob content comes before its path, so changes are tied to paths via marks."""
    out, i, in_blob, mark, pending = [], 0, False, None, {}
    while i < len(stream):
        nl = stream.index(b"\n", i)
        line, i = stream[i:nl], nl + 1
        if line == b"blob":
            in_blob, mark = True, None
        elif in_blob and line.startswith(b"mark "):
            mark = line[5:]
        elif line.startswith(b"data "):
            size = int(line[5:]); body = stream[i:i + size]; i += size
            if in_blob:
                changes = collections.Counter(); fields = set()
                if strip_meta and meta.kind(body):
                    fields = {f for f, _ in meta.extract(body)}
                    if fields:
                        body = meta.strip(body) or body
                if b"\x00" not in body[:8000]:
                    for old, new in reps:
                        if body.count(old):
                            changes[(old, new)] += body.count(old); body = body.replace(old, new)
                if changes or fields:
                    pending[mark] = (changes, fields)
            else:
                body = subst(body, reps, rep, "message")
            out.append(b"data %d\n" % len(body) + body)
            in_blob = False
            continue
        elif line.startswith((b"M ", b"D ")):
            parts = line.split(b" ", 3)
            path = unquote(parts[3] if line.startswith(b"M ") else line[2:])
            if any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(Path(path).name, g) for g in removes):
                if line.startswith(b"M "): rep.removed[path] += 1
                continue
            if line.startswith(b"M ") and parts[2] in pending:
                changes, fields = pending[parts[2]]
                for (o, n), c in changes.items():
                    key = (o.decode("utf-8", "replace"), n.decode("utf-8", "replace"))
                    rep.text[key] += c; rep.text_files[key].add(path)
                if fields: rep.meta[path] |= fields
        elif line.startswith((b"author ", b"committer ", b"tagger ")):
            role, rest = line.split(b" ", 1)
            end = rest.rindex(b">") + 1
            old = rest[:end]
            new = ident or subst(old, reps, Report(), "message")
            if new != old: rep.idents[(old.decode("utf-8", "replace"), new.decode("utf-8", "replace"))] += 1
            line = role + b" " + new + rest[end:]
        out.append(line + b"\n")
    return b"".join(out)


def fresh_tree(repo, reps, removes, strip_meta, rep, apply):
    """--fresh: clean the current files (no history involved)."""
    for p in filter(None, git(repo, "ls-files", "-z").decode().split("\0")):
        f = Path(repo, p)
        if any(fnmatch.fnmatch(p, g) or fnmatch.fnmatch(f.name, g) for g in removes):
            rep.removed[p] += 1
            if apply: git(repo, "rm", "-q", "--cached", "--", p); f.unlink(missing_ok=True)
            continue
        if not f.is_file() or f.is_symlink():
            continue
        b = nb = f.read_bytes()
        if strip_meta and meta.kind(b):
            fields = {k for k, _ in meta.extract(b)}
            if fields: rep.meta[p] |= fields; nb = meta.strip(b) or b
        if b"\x00" not in nb[:8000]:
            nb = subst(nb, reps, rep, "file", p)
        if apply and nb != b: f.write_bytes(nb)


def count_removed(repo, rep):
    """fast-export only lists a path when it changes, so ask each commit's tree whether it holds the path."""
    commits = git(repo, "rev-list", "--all").decode().split()
    if not rep.removed or not commits:
        return
    q = "".join(f"{c}:{p}\n" for p in rep.removed for c in commits)
    found = git(repo, "cat-file", "--batch-check", data=q.encode()).decode().splitlines()
    for i, p in enumerate(list(rep.removed)):
        rep.removed[p] = sum(not l.endswith(" missing") for l in found[i * len(commits):(i + 1) * len(commits)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--replace", action="append", default=[])
    ap.add_argument("--replace-file")
    ap.add_argument("--remove-path", action="append", default=[])
    ap.add_argument("--strip-metadata", action="store_true")
    ap.add_argument("--set-identity")
    ap.add_argument("--fresh", metavar="MESSAGE")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()

    if git(a.repo, "rev-parse", "--is-bare-repository").decode().strip() == "true":
        sys.exit("bare repository: clean.py needs a working tree. Run it on a normal clone (git clone REPO) instead")
    repo = git(a.repo, "rev-parse", "--show-toplevel").decode().strip()
    lines = list(a.replace) + ([l for l in Path(a.replace_file).read_text().splitlines() if l.strip()] if a.replace_file else [])
    reps = []
    for l in lines:
        if "==>" not in l: sys.exit(f"bad replacement, need OLD==>NEW: {redact('x', l)}")
        o, n = l.split("==>", 1); reps.append((o.encode(), n.encode()))
    reps.sort(key=lambda r: len(r[0]), reverse=True)  # "John Doe" before "John"
    ident = a.set_identity.encode() if a.set_identity else None
    if ident and not re.fullmatch(rb"[^<>\n]+ <[^<>\s]+>", ident):
        sys.exit('--set-identity must look like "Name <email>"')
    if a.apply:
        if git(repo, "status", "--porcelain", "--untracked-files=no").strip():
            sys.exit("uncommitted changes: commit or stash them first")
        if git(repo, "stash", "list").strip():
            sys.exit("stash not empty: it keeps old data alive. Apply or drop it first")

    rep, before = Report(), git(repo, "rev-list", "--all", "--count").decode().strip()
    branch = git(repo, "symbolic-ref", "--short", "HEAD").decode().strip()
    refs = git(repo, "for-each-ref", "--format=%(refname)").decode().split()
    if a.fresh:
        fresh_tree(repo, reps, a.remove_path, a.strip_metadata, rep, a.apply)
        doomed = [r for r in refs if r != f"refs/heads/{branch}"]
    else:
        stream = git(repo, "-c", "core.quotePath=false", "fast-export", "--branches", "--tags", "--signed-tags=strip",
                     "--tag-of-filtered-object=rewrite", "--reencode=yes", "--use-done-feature")
        new = rewrite(stream, reps, a.remove_path, ident, a.strip_metadata, rep)
        doomed = [r for r in refs if not r.startswith(("refs/heads/", "refs/tags/"))]
    count_removed(repo, rep)

    if a.apply:
        if not a.no_backup:
            bak = f"{repo}-backup-{time.strftime('%Y%m%d-%H%M%S')}.git"
            subprocess.run(["git", "clone", "-q", "--mirror", repo, bak], check=True)
        if a.fresh:
            env = dict(os.environ)
            if ident:
                name, email = ident.decode()[:-1].split(" <")
                env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
            git(repo, "checkout", "-q", "--orphan", "__fresh__"); git(repo, "add", "-u")
            git(repo, "commit", "-qm", a.fresh, env=env)
            for r in refs: git(repo, "update-ref", "-d", r)
            git(repo, "branch", "-m", branch)
        else:
            git(repo, "fast-import", "--force", "--quiet", data=new)
            for r in doomed: git(repo, "update-ref", "-d", r)
            git(repo, "reset", "-q", "--hard", "HEAD")
        git(repo, "reflog", "expire", "--expire=now", "--all")
        git(repo, "gc", "-q", "--prune=now", "--aggressive")

    rep.show(a.apply)
    print("\n## History")
    if a.fresh:
        print(f"  - {before} commits {'replaced' if a.apply else 'would be replaced'} by 1 commit on '{branch}'")
    else:
        print(f"  - all {before} commits on branches/tags {'rewritten' if a.apply else 'would be rewritten'} (new commit hashes)")
    for r in doomed: print(f"  - ref {'deleted' if a.apply else 'would be deleted'}: {r}")
    if a.apply:
        print(f"  - reflog expired, gc --prune=now done; commits now: {git(repo, 'rev-list', '--all', '--count').decode().strip()}")
        print(f"  - backup: {bak}" if not a.no_backup else "  - no backup made")
        print("\nNot pushed. Next: rescan, then force-push only with the user's OK.")
    else:
        print("\nNothing written. Re-run with --apply after the user agrees.")


if __name__ == "__main__":
    main()
