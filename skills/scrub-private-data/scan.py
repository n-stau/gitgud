#!/usr/bin/env python3
"""Scan a git repo (working tree + every blob in history + commit/tag messages + commit identities) for secrets and personal data.

Stdlib only. Matches are redacted in the output so secrets never land in a transcript.
Usage: scan.py [REPO] [--term TEXT ...] [--no-history]
Exit code: 0 = nothing found, 1 = findings.
"""
import argparse, getpass, os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta

TERMS_FILE = Path(os.environ.get("SCRUB_TERMS", Path.home() / ".config/scrub-private-data/terms.txt"))
MAX = 2_000_000  # text scan limit
META_MAX = 50_000_000  # shortcut: files above 50 MB are not read at all, use gitleaks/exiftool for huge assets

# (rule, severity, regex). Order matters: first match per span wins.
RULES = [
    ("private-key", "HIGH", r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY(?: BLOCK)?-----"),
    ("aws-key", "HIGH", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("github-token", "HIGH", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    ("gitlab-token", "HIGH", r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    ("anthropic-key", "HIGH", r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    ("openai-key", "HIGH", r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}"),
    ("resend-key", "HIGH", r"\bre_[A-Za-z0-9]{8}_[A-Za-z0-9]{16,}"),
    ("supabase-secret-key", "HIGH", r"\bsb_secret_[A-Za-z0-9_-]{20,}"),
    ("npm-token", "HIGH", r"\bnpm_[A-Za-z0-9]{36}\b"),
    ("huggingface-token", "HIGH", r"\bhf_[A-Za-z0-9]{30,}\b"),
    ("google-api-key", "HIGH", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("slack-token", "HIGH", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ("stripe-key", "HIGH", r"\b[rs]k_live_[A-Za-z0-9]{20,}"),
    ("discord-token", "HIGH", r"\b[MNO][A-Za-z\d_-]{23,27}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,40}\b"),
    ("webhook-url", "HIGH", r"https://(?:discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services)/[^\s\"'<>]+"),
    ("telegram-token", "HIGH", r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"),
    ("jwt", "HIGH", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ("url-credentials", "HIGH", r"\b[a-z][a-z0-9+.-]*://[^\s/:@\"']+:[^\s/@\"']+@[^\s\"']+"),
    ("secret-assignment", "MEDIUM",
     r"(?i)\b[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|client[_-]?secret|access[_-]?key|auth[_-]?key)[\w.-]*[\"']?\s*[:=]\s*[\"']?([^\s\"'`,;)]{6,})"),
    ("email", "MEDIUM", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("phone", "MEDIUM", r"(?<![\w.])(?:\+\d{2,3}[\s/-]?|\b0)1\d{2,3}[\s/-]?\d{3,4}[\s/-]?\d{3,5}\b|(?<![\w.])\+\d{2,3}[\s/-]?\d{2,5}[\s/-]?\d{3,}[\s/-]?\d{2,}\b"),
    ("iban", "MEDIUM", r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b"),
    ("home-path", "MEDIUM", r"(?:/Users/|/home/|[A-Za-z]:\\\\?Users\\\\?)(?!Shared\b|runner\b|user\b|username\b|you\b|example\b|node\b|ubuntu\b|app\b|vscode\b|codespace\b|jovyan\b)[A-Za-z0-9._-]+"),
    ("ip-address", "LOW", r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])"),
    ("mac-address", "LOW", r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"),
    ("gps-coordinates", "LOW", r"(?<![\w.])-?\d{1,2}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}(?![\w.])"),
    ("postcode-city", "LOW", r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]{2,}(?:\s(?:am|an|im)\s[A-ZÄÖÜ][a-zäöüß]+)?\b"),
]
RULES = [(n, s, re.compile(p)) for n, s, p in RULES]

PLACEHOLDER = re.compile(r"(?i)^(?:x+|\*+|\.+|changeme|change_me|password|secret|token|example|dummy|test|none|null|true|false|"
                         r"[\^~]?\d+(?:\.\d+)*|.*\(.*|[A-Za-z_][A-Za-z_.\[\]-]*|[{\[].*|f\..*|your[_-].*|<.*>|\$\{.*|\$\(.*|\{\{.*|os\.environ.*|process\.env.*|getenv.*|env\(.*|settings\..*|config\..*)$")
FILE_TLD = re.compile(r"(?i)\.(?:fbx|obj|glb|gltf|png|jpe?g|gif|svg|wav|mp3|ogg|py|js|ts|tsx|cs|json|md|txt|ya?ml|route|anim|mat|prefab|asset|unity|meta|lock)$")
SAFE_EMAIL = re.compile(r"(?i)@(?:users\.noreply\.github\.com|(?:example|beispiel)\.(?:com|org|net|de)|localhost|test|anthropic\.com)$|^noreply@|^no-reply@")
SAFE_IP = {"127.0.0.1", "0.0.0.0", "255.255.255.255", "255.255.255.0", "8.8.8.8", "1.1.1.1"}

SENSITIVE_NAMES = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:\..+)?|.*\.(?:pem|key|p12|pfx|jks|keystore|kdbx|ovpn|tfstate(?:\.backup)?|sqlite3?|db|log)|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)|\.netrc|\.npmrc|\.pypirc|\.pgpass|\.htpasswd|credentials(?:\.json)?|"
    r"service[-_]?account.*\.json|client_secret.*\.json|secrets?\.(?:json|ya?ml|toml)|\.DS_Store|Thumbs\.db|desktop\.ini|\._.+|"
    r".*\.(?:csproj|sln|vcxproj)\.user|\.idea/workspace\.xml)$")
LOCKFILES = re.compile(r"(?:^|/)(?:package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|poetry\.lock|Pipfile\.lock|"
                       r"Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock|packages\.lock\.json|uv\.lock)$")
EXAMPLE_NAMES = re.compile(r"(?i)\.(?:example|sample|template|dist)$")


def git(repo, *args, data=None):
    return subprocess.run(["git", "-C", repo, *args], input=data, capture_output=True, check=True).stdout


SHOW = {"sensitive-file", "exif-gps", "file-metadata", "commit-identity", "remote-with-credentials", "private-term", "email",
        "phone", "home-path", "ip-address", "mac-address", "gps-coordinates", "postcode-city"}


def redact(rule, s):
    """Personal data is shown so it can be judged; secrets are cut so they never reach logs or transcripts."""
    s = s.strip()
    return s if rule in SHOW or len(s) <= 6 else f"{s[:4]}…({len(s)} chars)"


def scan_text(text, terms, high_only=False):
    for ln, line in enumerate(text.splitlines(), 1):
        if len(line) > 5000:
            continue  # minified/generated line
        taken = []
        for t in terms:  # boundary on both sides, but "JohnDoe" (camelCase) still counts
            for m in re.finditer(r"(?<![A-Za-z0-9])(?i:" + re.escape(t) + r")(?![a-z0-9])", line):
                yield ln, "private-term", "HIGH", m.group(0)
        for name, sev, rx in RULES:
            if high_only and sev != "HIGH":
                continue
            for m in rx.finditer(line):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue
                val = m.group(m.lastindex or 0)
                if name == "secret-assignment" and PLACEHOLDER.match(val.strip("\"'")):
                    continue
                if name == "phone" and re.search(r"0{6,}", re.sub(r"\D", "", val)):
                    continue  # placeholder number
                if name == "email" and (SAFE_EMAIL.search(val) or FILE_TLD.search(val)):
                    continue
                if name == "ip-address" and (val in SAFE_IP or re.search(r"(?i)version|v\d", line)):
                    continue
                taken.append(m.span()); yield ln, name, sev, val


AUTH_CONFIGS = re.compile(r"(?:^|/)\.(?:npmrc|pypirc|netrc|yarnrc(?:\.yml)?)$")
IDENTIFYING_META = re.compile(r"(?i)artist|author|creator$|lastmodifiedby|owner|copyright|serial|company|manager|xpauthor|xpcomment|gps|initials|description")


def scan_blob(path, data, terms):
    if SENSITIVE_NAMES.search(path) and not EXAMPLE_NAMES.search(path):
        if not AUTH_CONFIGS.search(path) or re.search(rb"(?i)_auth|token|password|login", data):
            yield 0, "sensitive-file", "HIGH", Path(path).name
    if meta.kind(data):
        fields = meta.extract(data)
        if ("GPS", "location") in fields:
            yield 0, "exif-gps", "HIGH", "photo contains GPS location"
        rest = [f"{k}={v}" for k, v in fields if k != "GPS"]
        if rest:  # names/owners/serials matter; tool names and timestamps are only LOW
            ident = any(IDENTIFYING_META.search(k.split(":")[-1]) for k, _ in fields if k != "GPS")
            yield 0, "file-metadata", "MEDIUM" if ident else "LOW", "; ".join(rest)[:300]
            yield from ((0, r, "HIGH", v) for _, r, _, v in scan_text("\n".join(rest), terms) if r == "private-term")
        return
    if len(data) > MAX:
        return
    if b"\x00" in data[:8000]:  # binary (compiled app, archive): only build paths and private terms are meaningful
        text = data.decode("latin-1")
        yield from ((ln, r, s, v) for ln, r, s, v in scan_text(text, terms) if r in ("home-path", "private-term"))
        return
    yield from scan_text(data.decode("utf-8", "replace"), terms, high_only=bool(LOCKFILES.search(path)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--term", action="append", default=[], help="private text to find (name, street, city, phone…)")
    ap.add_argument("--no-history", action="store_true", help="only working tree (fast, e.g. pre-commit)")
    a = ap.parse_args()

    bare = git(a.repo, "rev-parse", "--is-bare-repository").decode().strip() == "true"
    repo = git(a.repo, "rev-parse", "--absolute-git-dir" if bare else "--show-toplevel").decode().strip()
    if bare:
        print("note: bare repository, no working tree: scanning history only\n")
    terms = {t for t in a.term if len(t) >= 3}
    if TERMS_FILE.is_file():  # personal default terms, kept outside any repo
        terms |= {l.strip() for l in TERMS_FILE.read_text().splitlines() if len(l.strip()) >= 3 and not l.startswith("#")}
    for k in ("user.name", "user.email"):
        v = subprocess.run(["git", "-C", repo, "config", k], capture_output=True, text=True).stdout.strip()
        if v and not SAFE_EMAIL.search(v) and (k == "user.email" or " " in v):  # "n-stau" is a public handle
            terms.add(v)
    if len(getpass.getuser()) >= 3:
        terms.add(getpass.getuser())
    terms = sorted({t.lower(): t for t in terms}.values(), key=len, reverse=True)  # matching is case-insensitive

    findings = {}  # (path, rule, value) -> (sev, line, where)
    seen = {}  # key -> how often the same value repeats in that file
    def add(path, hits, where):
        for ln, rule, sev, val in hits:
            k = (path, rule, val)
            findings.setdefault(k, (sev, ln, where)); seen[k] = seen.get(k, 0) + 1

    tree = [] if bare else git(repo, "ls-files", "-z", "-co", "--exclude-standard").decode().split("\0")
    for p in filter(None, tree):
        f = Path(repo, p)
        if f.is_file() and not f.is_symlink() and f.stat().st_size <= META_MAX:
            add(p, scan_blob(p, f.read_bytes(), terms), "tree")
    current = set() if bare else {l.split()[1] for l in git(repo, "ls-files", "-s").decode().splitlines()}  # already scanned above

    if not a.no_history and git(repo, "rev-list", "-n1", "--all").strip():
        objs = {}
        for line in git(repo, "rev-list", "--all", "--objects").decode().splitlines():
            sha, _, path = line.partition(" ")
            if path and sha not in current:
                objs.setdefault(sha, path)
        info = git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                   data="\n".join(objs).encode()).decode().split("\n")
        blobs = [p[0] for p in map(str.split, info) if len(p) == 3 and p[1] == "blob" and int(p[2]) <= META_MAX]
        out = git(repo, "cat-file", "--batch", data="\n".join(blobs).encode())
        pos = 0
        while pos < len(out):
            nl = out.index(b"\n", pos); sha, _, size = out[pos:nl].decode().split(); size = int(size)
            add(objs[sha], scan_blob(objs[sha], out[nl + 1:nl + 1 + size], terms), f"{'history' if bare else 'history-only'} blob {sha[:10]}")
            pos = nl + 2 + size
        msgs = git(repo, "log", "--all", "--format=%H%x00%B%x00").decode("utf-8", "replace").split("\0")
        tags = git(repo, "for-each-ref", "refs/tags", "--format=%(objectname)%00%(contents)%00").decode("utf-8", "replace").split("\0")
        for kind, chunk in (("commit message", msgs), ("tag message", tags)):
            for sha, body in zip(chunk[0::2], chunk[1::2]):
                add(f"({kind} {sha.strip()[:10]})", scan_text(body, terms), "history")
        idents = git(repo, "log", "--all", "--format=%an <%ae>%n%cn <%ce>").decode().splitlines()
        idents += git(repo, "for-each-ref", "refs/tags", "--format=%(taggername) %(taggeremail)").decode().split("\n")
        for ident in sorted(i for i in set(idents) if "<" in i):
            email = ident[ident.rfind("<") + 1:-1]
            if not SAFE_EMAIL.search(email) and email != "noreply@github.com":
                findings.setdefault(("(commit metadata)", "commit-identity", ident), ("MEDIUM", 0, "git log"))

    for line in git(repo, "remote", "-v").decode().splitlines():
        if re.search(r"://[^/\s]+@", line) and "git@" not in line:
            findings.setdefault((".git/config", "remote-with-credentials", line.split()[0]), ("HIGH", 0, "remote"))

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows = sorted(findings.items(), key=lambda kv: (order[kv[1][0]], kv[0][1], kv[0][0], kv[1][1]))
    low_seen = {}
    for (path, rule, val), (sev, ln, where) in rows:
        if sev == "LOW":  # LOW is noisy (test data, docs): one line per file and rule
            low_seen[(path, rule)] = low_seen.get((path, rule), 0) + 1
            if low_seen[(path, rule)] > 1:
                continue
        loc = f"{path}:{ln}" if ln else path
        more = seen.get((path, rule, val), 1) - 1
        print(f"{sev:6} {rule:22} {loc}  [{where}]  {redact(rule, val)}{f'  (+{more} more in this file)' if more else ''}")
    for (path, rule), n in low_seen.items():
        if n > 1:
            print(f"LOW    {rule:22} {path}  … {n - 1} more in this file")
    counts = {s: sum(1 for v in findings.values() if v[0] == s) for s in order}
    print(f"\n{len(findings)} findings  HIGH={counts['HIGH']} MEDIUM={counts['MEDIUM']} LOW={counts['LOW']}"
          f"  (terms checked: {len(terms)}, history: {'no' if a.no_history else 'yes'})")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
