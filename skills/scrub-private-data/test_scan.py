#!/usr/bin/env python3
"""Self-test: plant private data (files, deleted history, commit message, identities, photo/PDF/Office metadata)
in a throwaway repo, then check: scan finds it, dry run writes nothing, --apply removes it everywhere, rescan is clean."""
import io, struct, subprocess, sys, tempfile, zipfile
from pathlib import Path

HERE = Path(__file__).parent
KEY = "sk-ant-api03-" + "A1b2C3d4" * 6
RESEND = "re_" + "PbLm1234" + "_" + "abcdefghij" * 2   # fake keys built at runtime: no key pattern in the source
NAME, MAIL = "John Doe", "john.doe@private-mail.net"


def run(*a, cwd):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True)


def jpeg_with_meta():
    artist = NAME.encode() + b"\x00"
    ifd = struct.pack("<H", 2) + struct.pack("<HHII", 0x013B, 2, len(artist), 38) + struct.pack("<HHII", 0x8825, 4, 1, 0) + struct.pack("<I", 0)
    tiff = b"II*\x00" + struct.pack("<I", 8) + ifd + artist
    app1 = b"Exif\x00\x00" + tiff
    return b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xda\x00\x02\xff\xd9"


def docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("docProps/core.xml", f"<cp:coreProperties><dc:creator>{NAME}</dc:creator><cp:lastModifiedBy>{NAME}</cp:lastModifiedBy></cp:coreProperties>")
    return buf.getvalue()


def scan(d, *extra):
    r = run(sys.executable, str(HERE / "scan.py"), d, "--term", "Market Street", *extra, cwd=d)
    return r.returncode, r.stdout


with tempfile.TemporaryDirectory() as root:
    d = str(Path(root, "repo")); Path(d).mkdir()
    for c in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.name", NAME], ["git", "config", "user.email", MAIL]):
        run(*c, cwd=d)
    Path(d, ".env").write_text(f"ANTHROPIC_API_KEY={KEY}\nDB_PASSWORD=hunter2hunter2\n")
    run("git", "add", ".", cwd=d); run("git", "commit", "-qm", "init", cwd=d)
    Path(d, "README.md").write_text("demo\n"); run("git", "add", ".", cwd=d); run("git", "commit", "-qm", "readme", cwd=d)
    run("git", "rm", "-q", ".env", cwd=d); run("git", "commit", "-qm", f"remove env, key was {KEY}", cwd=d)
    Path(d, "app.py").write_text('API_KEY = os.environ["API_KEY"]\npath = "/Users/john/nas/photos"\n'
                                 f'contact = "{MAIL}"  # tel +49 171 2345678\nHOST = "192.168.178.23"\n'
                                 'addr = "Market Street 12, 70173 Stuttgart"\n'
                                 f'RESEND = "{RESEND}"\nclip = "Name@Clip.fbx"\ntokens = total_tokens\n'
                                 'bundle = "com.JohnDoe.App"\n')
    Path(d, "pic.jpg").write_bytes(jpeg_with_meta())
    Path(d, "cv.pdf").write_bytes(f"%PDF-1.4\n1 0 obj << /Author ({NAME}) /Producer (TeX) >> endobj\n%%EOF\n".encode())
    Path(d, "notes.docx").write_bytes(docx())
    run("git", "add", ".", cwd=d); run("git", "commit", "-qm", "app", cwd=d)

    # 1. scan finds everything, never prints the secret
    code, out = scan(d, "--term", "John")
    print(out)
    assert code == 1 and KEY not in out and "hunter2hunter2" not in out, "secret leaked into output"
    for rule in ("anthropic-key", "secret-assignment", "sensitive-file", "exif-gps", "file-metadata", "home-path", "phone",
                 "ip-address", "postcode-city", "private-term", "commit-identity", "(commit message"):
        assert rule in out, rule
    assert "history-only blob" in out and 'os.environ' not in out
    assert "resend-key" in out and "Name@Clip.fbx" not in out and "total_tokens" not in out
    assert "app.py:9" in out, "camelCase name in bundle id missed"

    # 1b. bare clone: scan reads history only without crashing, clean refuses
    bare = str(Path(root, "bare.git")); run("git", "clone", "-q", "--bare", d, bare, cwd=root)
    code, out = scan(bare)
    assert code == 1 and "bare repository" in out and "anthropic-key" in out and "Traceback" not in out, out
    r = run(sys.executable, str(HERE / "clean.py"), bare, "--remove-path", ".env", cwd=root)
    assert r.returncode and "bare repository" in r.stderr and "Traceback" not in r.stderr, r.stderr

    # 2. dry run writes nothing
    head = run("git", "rev-parse", "HEAD", cwd=d).stdout
    args = [sys.executable, str(HERE / "clean.py"), d, "--remove-path", ".env", "--strip-metadata",
            "--set-identity", "Jane Doe <jane@example.com>",
            "--replace", f"{KEY}==>REDACTED", "--replace", f"{NAME}==>Jane Doe", "--replace", f"{MAIL}==>jane@example.com",
            "--replace", "/Users/john==>/path/to", "--replace", "Market Street 12, 70173 Stuttgart==>Example Street 1",
            "--replace", "+49 171 2345678==>+49 000 0000000", "--replace", "192.168.178.23==>127.0.0.1",
            "--replace", f"{RESEND}==>REDACTED", "--replace", "JohnDoe==>JaneSmith"]
    dry = run(*args, cwd=d).stdout
    print(dry)
    assert "DRY RUN" in dry and run("git", "rev-parse", "HEAD", cwd=d).stdout == head
    assert KEY not in dry
    assert ".env  (2 commits)" in dry, "removed-file count must be commits containing it, not commits changing it"
    for want in (".env", "app.py", "pic.jpg", "cv.pdf", "notes.docx", "Jane Doe <jane@example.com>", "commit/tag messages"):
        assert want in dry, want

    # 3. apply, then everything is gone from files, history, messages, identities and metadata
    done = run(*args, "--apply", cwd=d)
    print(done.stdout, done.stderr)
    assert "CHANGED" in done.stdout and "backup:" in done.stdout and KEY not in done.stdout
    assert list(Path(root).glob("repo-backup-*.git")), "no backup"
    run("git", "config", "user.email", "jane@example.com", cwd=d)
    code, out = scan(d, "--term", "John")
    print(out)
    assert code == 0 and "file-metadata" not in out and "commit-identity" not in out and "history-only" not in out, out
    assert "Market Street 12, 70173 Stuttgart" in done.stdout and "hunter2hunter2" not in done.stdout
    assert "Example Street 1" in Path(d, "app.py").read_text()
print("OK")
