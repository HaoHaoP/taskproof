"""Verification contract.

Covers the two ways a worker's success claim is overruled, plus the rule that a
skipped acceptance is NOT a pass.
"""

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from taskproof import verify


class ForbiddenPathTest(unittest.TestCase):
    def test_direct_match(self):
        hits = verify.check_forbidden("/repo", ["dist/"], ["dist/app.js"])
        self.assertEqual(hits, ["dist/app.js"])

    def test_nested_under_forbidden_dir(self):
        hits = verify.check_forbidden("/repo", ["build/"], ["build/sub/deep.o"])
        self.assertEqual(hits, ["build/sub/deep.o"])

    def test_leading_dot_slash_normalised(self):
        hits = verify.check_forbidden("/repo", ["dist/"], ["./dist/app.js"])
        self.assertEqual(hits, ["./dist/app.js"])

    def test_clean_change_not_flagged(self):
        self.assertEqual(verify.check_forbidden("/repo", ["dist/"], ["src/main.py"]), [])

    def test_file_rule_matches_exact_file_only(self):
        self.assertEqual(verify.check_forbidden("/repo", [".git/config"], ["src/x.py"]), [])

    def test_absolute_forbidden_entry(self):
        hits = verify.check_forbidden("/repo", ["/repo/dist/"], ["dist/app.js"])
        self.assertEqual(hits, ["dist/app.js"])


class ForbiddenSnapshotTest(unittest.TestCase):
    """The guard cannot rest on the git change list.

    git reports nothing inside `.git/`, and it omits every ignored path -- which
    is what build output and dependency directories are. Measured: with
    `forbidden_paths = ["dist/"]` and `dist/` in `.gitignore`, an adapter wrote
    `dist/app.js` and the run was recorded as `done`.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workdir = self._tmp.name
        os.makedirs(os.path.join(self.workdir, ".git"))
        os.makedirs(os.path.join(self.workdir, "dist"))

    def tearDown(self):
        self._tmp.cleanup()

    def _snapshot(self, *rules):
        return verify.snapshot_forbidden(self.workdir, list(rules))

    def test_sees_a_write_inside_dot_git(self):
        before, _ = self._snapshot(".git/")
        with open(os.path.join(self.workdir, ".git", "sneaky.txt"), "w") as handle:
            handle.write("x")
        after, _ = self._snapshot(".git/")
        self.assertIn(".git/sneaky.txt", verify.diff_snapshots(before, after))

    def test_sees_a_write_under_an_ignored_path(self):
        before, _ = self._snapshot("dist/")
        with open(os.path.join(self.workdir, "dist", "app.js"), "w") as handle:
            handle.write("built")
        after, _ = self._snapshot("dist/")
        self.assertIn("dist/app.js", verify.diff_snapshots(before, after))

    def test_untouched_protected_path_is_not_a_violation(self):
        before, _ = self._snapshot(".git/", "dist/")
        after, _ = self._snapshot(".git/", "dist/")
        self.assertEqual(verify.diff_snapshots(before, after), [])

    def test_records_a_modification_and_a_removal(self):
        keep = os.path.join(self.workdir, "dist", "keep.js")
        drop = os.path.join(self.workdir, "dist", "drop.js")
        for path in (keep, drop):
            with open(path, "w") as handle:
                handle.write("one")
        before, _ = self._snapshot("dist/")
        # Different size, so this does not depend on timestamp granularity.
        with open(keep, "w") as handle:
            handle.write("two-much-longer")
        os.remove(drop)
        after, _ = self._snapshot("dist/")
        changed = verify.diff_snapshots(before, after)
        self.assertIn("dist/keep.js", changed)
        self.assertIn("dist/drop.js", changed)

    def test_a_rule_that_does_not_exist_yet_is_caught_when_created(self):
        before, _ = self._snapshot("node_modules/")
        self.assertEqual(before, {})
        os.makedirs(os.path.join(self.workdir, "node_modules"))
        with open(os.path.join(self.workdir, "node_modules", "x.js"), "w") as handle:
            handle.write("dep")
        after, _ = self._snapshot("node_modules/")
        self.assertIn("node_modules/x.js", verify.diff_snapshots(before, after))

    def test_a_truncated_walk_says_so(self):
        original = verify.SNAPSHOT_LIMIT
        verify.SNAPSHOT_LIMIT = 3
        try:
            for index in range(5):
                with open(os.path.join(self.workdir, "dist", f"f{index}"), "w") as handle:
                    handle.write("x")
            entries, truncated = self._snapshot("dist/")
        finally:
            verify.SNAPSHOT_LIMIT = original
        self.assertTrue(truncated)
        self.assertLessEqual(len(entries), 3)


class GitStateSnapshotTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workdir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.workdir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _init_repo(self):
        self._git("init", "-q")
        self._git("config", "user.email", "probe@example.invalid")
        self._git("config", "user.name", "probe")

    def test_non_repo_is_empty(self):
        self.assertEqual(verify.git_state_snapshot(self.workdir), {})

    def test_git_missing_from_path_is_empty(self):
        with mock.patch.dict(os.environ, {"PATH": ""}):
            self.assertEqual(verify.git_state_snapshot(self.workdir), {})

    def test_commit_changes_head(self):
        self._init_repo()
        before = verify.git_state_snapshot(self.workdir)
        self._git("commit", "--allow-empty", "-qm", "probe")
        after = verify.git_state_snapshot(self.workdir)
        self.assertIn("HEAD", verify.diff_snapshots(before, after))

    def test_branch_change_is_visible(self):
        self._init_repo()
        self._git("commit", "--allow-empty", "-qm", "seed")
        before = verify.git_state_snapshot(self.workdir)
        self._git("checkout", "-q", "-b", "probe-branch")
        after = verify.git_state_snapshot(self.workdir)
        changed = verify.diff_snapshots(before, after)
        self.assertIn("symbolic-ref", changed)
        self.assertIn("refs/heads/probe-branch", changed)

    def test_status_index_refresh_is_not_state_change(self):
        self._init_repo()
        tracked = os.path.join(self.workdir, "tracked.txt")
        with open(tracked, "w") as handle:
            handle.write("seed\n")
        self._git("add", "tracked.txt")
        self._git("commit", "-qm", "seed")
        # Leave stale stat data so `git status` refreshes `.git/index`.
        os.utime(tracked, None)
        before = verify.git_state_snapshot(self.workdir)
        self._git("status", "--porcelain")
        after = verify.git_state_snapshot(self.workdir)
        self.assertEqual(verify.diff_snapshots(before, after), [])

    def test_stash_is_visible(self):
        self._init_repo()
        tracked = os.path.join(self.workdir, "tracked.txt")
        with open(tracked, "w") as handle:
            handle.write("seed\n")
        self._git("add", "tracked.txt")
        self._git("commit", "-qm", "seed")
        with open(tracked, "w") as handle:
            handle.write("changed\n")
        before = verify.git_state_snapshot(self.workdir)
        self._git("stash", "push", "-qm", "probe")
        after = verify.git_state_snapshot(self.workdir)
        self.assertIn("stash", verify.diff_snapshots(before, after))


class AcceptanceTest(unittest.TestCase):
    def test_no_command_is_skipped_not_passed(self):
        out = verify.run_acceptance("/tmp", None)
        self.assertFalse(out.ran)
        self.assertTrue(out.passed)
        self.assertIn("no acceptance command", out.note)

    def test_success(self):
        with tempfile.TemporaryDirectory() as d:
            out = verify.run_acceptance(d, "exit 0")
            self.assertTrue(out.ran)
            self.assertTrue(out.passed)
            self.assertEqual(out.exit_code, 0)

    def test_failure_records_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            out = verify.run_acceptance(d, "exit 7")
            self.assertTrue(out.ran)
            self.assertFalse(out.passed)
            self.assertEqual(out.exit_code, 7)

    def test_output_is_tailed(self):
        with tempfile.TemporaryDirectory() as d:
            out = verify.run_acceptance(d, "for i in $(seq 1 200); do echo line$i; done", tail_lines=5)
            self.assertIn("line200", out.output_tail)
            self.assertNotIn("line1\n", out.output_tail)

    def test_timeout_is_failure_not_error(self):
        with tempfile.TemporaryDirectory() as d:
            out = verify.run_acceptance(d, "sleep 5", timeout=1)
            self.assertTrue(out.ran)
            self.assertFalse(out.passed)
            self.assertIn("timeout", out.note.lower())


class DetectChangesTest(unittest.TestCase):
    def test_non_repo_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(verify.detect_changes(d))

    def test_untracked_file_counted(self):
        with tempfile.TemporaryDirectory() as d:
            os.system(f"cd {d} && git init -q && git config user.email t@t && git config user.name t")
            open(os.path.join(d, "new.txt"), "w").write("x")
            self.assertEqual(verify.detect_changes(d), 1)


if __name__ == "__main__":
    unittest.main()
