#!/usr/bin/env python3
"""Self-test for changelog.py: builds throwaway git repos with Conventional Commits and a tag,
then checks section grouping, hidden types, breaking changes, reverts, tag selection, --insert and --next-version."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("changelog.py")
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
       "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com"}
ROOT = tempfile.TemporaryDirectory()  # removed at exit with every repo inside


def git(d, *a):
    return subprocess.run(["git", "-C", d, *a], env=ENV, check=True, capture_output=True, text=True).stdout.strip()


def commit(d, *messages):
    for msg in messages:
        git(d, "commit", "-q", "--allow-empty", "-m", msg)
    return git(d, "rev-parse", "HEAD")


def repo(tag, *messages):
    """New repo with one chore commit, optional tag, then one empty commit per message."""
    d = tempfile.mkdtemp(dir=ROOT.name)
    git(d, "init", "-q", "-b", "main")
    commit(d, "chore: initial commit")
    if tag:
        git(d, "tag", "-a", tag, "-m", tag)
    commit(d, *messages)
    return d


def run(d, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", d, *args], capture_output=True, text=True)


class Changelog(unittest.TestCase):
    def test_grouping(self):
        d = repo("v1.2.3", "feat(api): add profile endpoint", "fix: handle empty input", "docs: fix typo",
                 "perf(db): cache lookups", "Update stuff", "fix(security): escape html")
        r = run(d, "--version", "1.3.0")
        out = r.stdout
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(out, r"^## \[1\.3\.0\] - \d{4}-\d\d-\d\d\n")
        self.assertLess(out.index("### Added"), out.index("### Changed"))
        self.assertLess(out.index("### Changed"), out.index("### Fixed"))
        self.assertLess(out.index("### Fixed"), out.index("### Security"))
        self.assertIn("- **api:** add profile endpoint (", out)
        self.assertIn("- handle empty input (", out)
        self.assertIn("- **db:** cache lookups (", out)
        self.assertIn("- **security:** escape html (", out)
        self.assertIn("### Other\n\n- Update stuff (", out)
        self.assertNotIn("fix typo", out)
        self.assertNotIn("initial commit", out)  # before the tag
        self.assertIn("not in Conventional Commits format", r.stderr)
        self.assertIn("fix typo", run(d, "--all").stdout)

    def test_next_version(self):
        cases = [
            ("v1.2.3", ["fix: a", "docs: b"], "1.2.4"),
            ("v1.2.3", ["fix: a", "feat(ui): b"], "1.3.0"),
            ("1.2.3", ["feat!: drop node 18"], "2.0.0"),
            ("v1.2.3", ["feat: a\n\nBREAKING CHANGE: config key renamed"], "2.0.0"),
            ("v0.4.1", ["feat!: new config format"], "0.5.0"),  # 0.x: breaking bumps minor
            (None, ["feat: first feature"], "0.1.0"),
        ]
        for tag, msgs, want in cases:
            with self.subTest(tag=tag, msgs=msgs):
                r = run(repo(tag, *msgs), "--next-version")
                self.assertEqual((r.returncode, r.stdout.strip()), (0, want), r.stderr)

    def test_breaking_rendering_and_default_heading(self):
        out = run(repo("v2.0.0", "refactor(core)!: rename Client to Session\n\nBREAKING CHANGE: use Session(...)")).stdout
        self.assertTrue(out.startswith("## [3.0.0] - "), out)
        self.assertIn("### Changed\n\n- **BREAKING:** **core:** rename Client to Session (", out)
        self.assertIn("\n  use Session(...)", out)

    def test_nothing_to_release(self):
        d = repo("v1.0.0", "docs: readme", "chore: bump deps", "refactor: tidy")
        r = run(d, "--next-version")
        self.assertEqual((r.returncode, r.stdout), (1, ""))
        self.assertIn("no release-worthy commits since v1.0.0", r.stderr)
        self.assertTrue(run(d).stdout.startswith("## [Unreleased]\n"))

    def test_to_tag_uses_previous_tag(self):  # regression: --to v1.3.0 resolved v1.3.0 itself, empty notes
        d = repo("v1.2.3", "feat: profile page")
        git(d, "tag", "-a", "v1.3.0", "-m", "v1.3.0")
        commit(d, "fix: later fix")
        out = run(d, "--to", "v1.3.0", "--version", "1.3.0").stdout
        self.assertIn("- profile page (", out)
        self.assertNotIn("later fix", out)
        self.assertEqual(run(d, "--next-version").stdout.strip(), "1.3.1")

    def test_revert_cancels_out(self):
        d = repo("v1.2.3", "fix: small fix")
        sha = commit(d, "feat: big feature")
        commit(d, f'Revert "feat: big feature"\n\nThis reverts commit {sha}.')
        r = run(d, "--next-version")
        self.assertEqual(r.stdout.strip(), "1.2.4", r.stderr)
        out = run(d).stdout
        self.assertNotIn("big feature", out)
        self.assertNotIn("Other", out)

    def test_tag_selection_skips_non_semver_and_prereleases(self):
        d = repo("v1.2.3", "feat: a")
        git(d, "tag", "2025-snapshot")
        self.assertEqual(run(d, "--next-version").stdout.strip(), "1.3.0")
        d = repo("v1.3.0-rc.1", "feat: a")
        git(d, "tag", "-a", "v1.3.0", "-m", "v1.3.0")
        commit(d, "fix: b")
        self.assertEqual(run(d, "--next-version").stdout.strip(), "1.3.1")  # v1.3.0 is newer than v1.3.0-rc.1

    def test_fixup_gitmoji_and_multiline_note(self):
        d = repo("v1.0.0", "fixup! feat: x", "squash! fix: y", ":sparkles: feat: shiny", "\U0001F41B fix(ui): bug",
                 "feat!: new api\n\nBREAKING CHANGE: first line\nsecond line\n\nunrelated\n\nRefs: #1")
        r = run(d, "--version", "2.0.0")
        self.assertNotIn("fixup!", r.stdout)
        self.assertNotIn("squash!", r.stdout)
        self.assertIn("- shiny (", r.stdout)
        self.assertIn("- **ui:** bug (", r.stdout)
        self.assertIn("\n  first line\n  second line\n", r.stdout)
        self.assertNotIn("unrelated", r.stdout)
        self.assertNotIn("not in Conventional Commits format", r.stderr)

    def test_insert(self):
        d = repo("v1.0.0", "fix: a")
        path = Path(d, "CHANGELOG.md")
        run(d, "--version", "1.0.1", "--insert", str(path))
        text = path.read_text()
        self.assertTrue(text.startswith("# Changelog\n"), text)
        self.assertIn("## [Unreleased]\n\n## [1.0.1] - ", text)
        commit(d, "feat: b")
        run(d, "--version", "1.1.0", "--insert", str(path))
        text = path.read_text()
        self.assertLess(text.index("## [Unreleased]"), text.index("## [1.1.0]"))
        self.assertLess(text.index("## [1.1.0]"), text.index("## [1.0.1]"))
        self.assertIn("(", text.split("## [1.0.1]")[1])  # old section kept intact
        path.write_text("# Changelog\n\n## [0.9.0] - 2020-01-01\n")
        run(d, "--version", "1.1.0", "--insert", str(path))
        self.assertRegex(path.read_text(), r"^# Changelog\n\n## \[Unreleased\]\n\n## \[1\.1\.0\][^\n]*\n(.|\n)*\n\n## \[0\.9\.0\]")


if __name__ == "__main__":
    unittest.main()
