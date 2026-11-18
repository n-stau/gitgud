#!/usr/bin/env python3
"""Changelog section (Keep a Changelog) and next semver version from Conventional Commits since the last tag.

Stdlib only, read-only unless --insert. Usage:
  changelog.py [--repo DIR] [--from REF] [--to REF] [--version X.Y.Z] [--all]   # prints a markdown section
  changelog.py --next-version                                                 # prints only the suggested version
  changelog.py --version X.Y.Z --insert CHANGELOG.md                          # also writes it below ## [Unreleased]
--from defaults to the newest semver tag (v1.2.3 or 1.2.3) reachable from --to^; without a tag, all history counts.
A revert and the commit it reverts cancel out when both are in the range; fixup!/squash! commits are skipped.
--next-version exits 1 when no commit warrants a release (only docs/chore/test/... or non-conventional subjects).
"""
import argparse, datetime, re, subprocess, sys
from pathlib import Path

SUBJECT = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: (?P<desc>.+)$")
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE: *(.*(?:\n(?![\w-]+(?:: | #)).+)*)", re.M)  # until blank line or trailer
GITMOJI = re.compile(r"^(?::\w+:|[^\w\s]+)\s*")  # leading :sparkles: or emoji before the type
REVERTS = re.compile(r"This reverts commit ([0-9a-f]{40,64})")
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")  # shortcut: a prerelease tag (v1.3.0-rc.1) counts as 1.3.0, pass --from <last stable tag> then
SECTIONS = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Other"]  # Keep a Changelog order
TYPE_SECTION = {"feat": "Added", "fix": "Fixed", "perf": "Changed", "refactor": "Changed", "revert": "Changed",
                "deprecate": "Deprecated", "remove": "Removed", "security": "Security"}
HIDDEN = {"docs", "test", "tests", "chore", "ci", "build", "style"}  # shown under Other only with --all
BUMP = {"feat": 2, "fix": 1, "perf": 1, "revert": 1, "security": 1, "deprecate": 1, "remove": 1}  # 3 major, 2 minor, 1 patch


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


HEADER = """# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
"""


def last_tag(repo, to):
    # <to>^ so that --to v1.3.0 finds the tag before it; versionsort.suffix sorts v1.3.0-rc.1 below v1.3.0
    r = git(repo, "-c", "versionsort.suffix=-", "tag", "--merged", f"{to}^", "--sort=-v:refname", check=False)
    return next((t for t in r.stdout.split() if VERSION.match(t)), None) if r.returncode == 0 else None


def commits(repo, frm, to):
    """Parsed commits, newest first, without fixup!/squash! commits and without reverts that cancel out."""
    out = git(repo, "log", "--no-merges", "--reverse", "--format=%H%x1f%h%x1f%s%x1f%b%x1e",
              f"{frm}..{to}" if frm else to).stdout
    kept = {}
    for rec in out.split("\x1e"):
        if rec.strip():
            full, sha, subject, body = (rec.strip("\n").split("\x1f") + ["", ""])[:4]
            reverted = REVERTS.search(body)
            if reverted and reverted[1] in kept:
                del kept[reverted[1]]
            elif not subject.startswith(("fixup! ", "squash! ", "amend! ")):
                kept[full] = parse(sha, subject, body)
    return list(reversed(kept.values()))


def parse(sha, subject, body):
    m = SUBJECT.match(GITMOJI.sub("", subject, 1))
    footer = BREAKING_FOOTER.search(body)
    note = "\n  ".join(l.strip() for l in footer[1].strip().splitlines()) if footer else None
    if not m:
        return {"sha": sha, "type": None, "scope": None, "desc": subject, "breaking": False, "note": None}
    return {"sha": sha, "type": m["type"].lower(), "scope": m["scope"] or None, "desc": m["desc"],
            "breaking": bool(m["bang"] or footer), "note": note or None}


def section_of(c, show_all):
    if c["type"] is None:
        return "Other"
    if c["scope"] == "security":
        return "Security"
    if c["type"] in TYPE_SECTION:
        return TYPE_SECTION[c["type"]]
    return "Other" if show_all or c["breaking"] or c["type"] not in HIDDEN else None


def next_version(current, cs):
    level = max([3 if c["breaking"] else BUMP.get(c["type"], 0) for c in cs] or [0])
    if not level:
        return None
    major, minor, patch = current
    if major == 0 and level == 3:
        level = 2  # 0.x: breaking changes bump the minor version (semver item 4)
    if level == 3:
        return f"{major + 1}.0.0"
    if level == 2:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def render(version, cs, show_all):
    head = f"## [{version}] - {datetime.date.today().isoformat()}" if version else "## [Unreleased]"
    groups = {s: [] for s in SECTIONS}
    for c in cs:
        s = section_of(c, show_all)
        if s:
            line = "- " + ("**BREAKING:** " if c["breaking"] else "") + (f"**{c['scope']}:** " if c["scope"] else "")
            line += f"{c['desc']} ({c['sha']})"
            groups[s].append(line + (f"\n  {c['note']}" if c["note"] else ""))
    out = [head]
    for s in SECTIONS:
        if groups[s]:
            out += ["", f"### {s}", ""] + groups[s]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--from", dest="frm", help="start ref (exclusive); default: last version tag")
    ap.add_argument("--to", default="HEAD")
    ap.add_argument("--version", help="version for the heading; default: the suggested next version")
    ap.add_argument("--all", action="store_true", help="also list docs/chore/test/ci/build/style commits")
    ap.add_argument("--next-version", action="store_true", help="print only the suggested next version")
    ap.add_argument("--insert", metavar="CHANGELOG", help="also insert the section below ## [Unreleased] (file created if missing)")
    a = ap.parse_args()

    frm = a.frm or last_tag(a.repo, a.to)
    m = VERSION.match(frm or "0.0.0")
    current = tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    cs = commits(a.repo, frm, a.to)
    other = sum(c["type"] is None for c in cs)
    if other:
        print(f"note: {other} commit(s) not in Conventional Commits format, check them by hand", file=sys.stderr)
    nxt = next_version(current, cs)
    if a.next_version:
        if not nxt:
            sys.exit(f"no release-worthy commits since {frm or 'the first commit'}")
        print(nxt)
        return
    section = render(a.version or nxt, cs, a.all)
    if a.insert:
        insert(Path(a.insert), section)
    print(section, end="")


def insert(path, section):
    text = path.read_text() if path.exists() else HEADER
    head = "## [Unreleased]"
    if head not in text:  # put it above the newest release, or at the end
        j = text.find("\n## [")
        text = text.rstrip("\n") + f"\n\n{head}\n" if j < 0 else f"{text[:j + 1]}{head}\n\n{text[j + 1:]}"
    i = text.index(head) + len(head)
    path.write_text(f"{text[:i]}\n\n{section.rstrip()}{text[i:]}")


if __name__ == "__main__":
    main()
