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

    def test_typed_path_prefixes_are_stripped_for_matching(self):
        self.assertEqual(
            verify.check_forbidden("/repo", ["file:dist/"], ["dist/app.js"]),
            ["dist/app.js"],
        )
        self.assertEqual(
            verify.check_forbidden(
                "/repo", ["presence:dist/"], ["dist/app.js"]
            ),
            ["dist/app.js"],
        )
        self.assertEqual(
            verify.check_forbidden("/repo", ["git:.git/"], ["src/main.py"]), []
        )


class PythonBytecodeExemptionTest(unittest.TestCase):
    """Running Python drops byte-code; that must never trip the changed-path gate.

    A worker that imports the package from inside a guarded tree writes
    ``__pycache__/*.pyc`` as a byproduct of *running* the tool. Counting it as a
    breach makes "forbid a Python source directory" unusable. The exemption is
    narrow: only a ``__pycache__`` directory segment or a ``.pyc`` / ``.pyo``
    ending, and a name that merely contains the substring is still a breach.
    """

    def test_pycache_directory_segment_is_exempt(self):
        self.assertTrue(
            verify.is_python_bytecode("t/__pycache__/mod.cpython-314.pyc")
        )
        self.assertTrue(verify.is_python_bytecode("__pycache__/mod.pyc"))

    def test_pyc_and_pyo_suffixes_are_exempt(self):
        self.assertTrue(verify.is_python_bytecode("t/mod.cpython-314.pyc"))
        self.assertTrue(verify.is_python_bytecode("t/mod.pyo"))

    def test_a_pycache_substring_is_not_exempt(self):
        # "contains pycache" is not "is the __pycache__ directory segment".
        self.assertFalse(verify.is_python_bytecode("a__pycache__b.py"))
        self.assertFalse(verify.is_python_bytecode("t/a__pycache__b.py"))
        self.assertFalse(verify.is_python_bytecode("t/mod.py"))

    def test_check_forbidden_skips_bytecode_for_every_rule_kind(self):
        # The path decides, not the rule: file / explicit file / presence alike.
        for rule in ("t/", "file:t/", "presence:t/"):
            self.assertEqual(
                verify.check_forbidden(
                    "/repo",
                    [rule],
                    ["t/__pycache__/mod.cpython-314.pyc", "t/mod.pyc"],
                ),
                [],
            )

    def test_check_forbidden_still_catches_human_edits(self):
        self.assertEqual(
            verify.check_forbidden(
                "/repo",
                ["t/"],
                ["t/keep.py", "t/a__pycache__b.py"],
            ),
            ["t/keep.py", "t/a__pycache__b.py"],
        )


class ForbiddenRuleParseTest(unittest.TestCase):
    def test_untyped_rule_is_file(self):
        rule = verify.parse_forbidden_rule("dist/")
        self.assertEqual((rule.kind, rule.path, rule.raw), ("file", "dist/", "dist/"))

    def test_explicit_file_rule(self):
        rule = verify.parse_forbidden_rule("file:dist/")
        self.assertEqual((rule.kind, rule.path), ("file", "dist/"))

    def test_presence_rule(self):
        rule = verify.parse_forbidden_rule("presence:dist/")
        self.assertEqual((rule.kind, rule.path), ("presence", "dist/"))

    def test_git_rule(self):
        rule = verify.parse_forbidden_rule("git:.git/")
        self.assertEqual((rule.kind, rule.path), ("git", ".git/"))


class ChangedFilesDiffTest(unittest.TestCase):
    def test_pre_existing_status_is_not_a_difference(self):
        before = {"noise/.DS_Store": "??"}
        after = {"noise/.DS_Store": "??"}
        self.assertEqual(verify.diff_changed_files(before, after), [])

    def test_added_removed_and_status_changed_paths(self):
        before = {"kept.txt": " M", "gone.txt": "??"}
        after = {"kept.txt": "A ", "new.txt": "??"}
        self.assertEqual(
            verify.diff_changed_files(before, after),
            ["gone.txt", "kept.txt", "new.txt"],
        )


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

    def test_presence_ignores_content_change_but_sees_add_and_remove(self):
        keep = os.path.join(self.workdir, "dist", "keep.js")
        with open(keep, "w") as handle:
            handle.write("one")
        before, _ = self._snapshot("dist/")

        # Same path set, different fingerprints: presence must stay quiet.
        with open(keep, "w") as handle:
            handle.write("two-much-longer")
        content_only, _ = self._snapshot("dist/")
        self.assertEqual(
            verify.diff_presence_snapshots(before, content_only), []
        )

        added = os.path.join(self.workdir, "dist", "new.js")
        with open(added, "w") as handle:
            handle.write("new")
        after_add, _ = self._snapshot("dist/")
        self.assertEqual(
            verify.diff_presence_snapshots(before, after_add), ["dist/new.js"]
        )

        os.remove(keep)
        after_remove, _ = self._snapshot("dist/")
        # Removal is spotted relative to the state that still had the file.
        self.assertEqual(
            verify.diff_presence_snapshots(after_add, after_remove),
            ["dist/keep.js"],
        )


class GitStateSnapshotTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # The repo lives one level down so a sibling worktree can sit beside it
        # under the same unique temp dir (a worktree cannot be nested in the
        # checkout it was added from).
        self.workdir = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.workdir)

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

    # -- card67: refs/heads is shared across worktrees --------------------

    def _git_in(self, cwd, *args):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _seed_commit(self, name="seed.txt"):
        with open(os.path.join(self.workdir, name), "w") as handle:
            handle.write("seed\n")
        self._git("add", name)
        self._git("commit", "-qm", "seed")

    def _legacy_snapshot(self):
        """The pre-card67 probe: every ref, no worktree exclusion at all."""
        state = {"HEAD": "", "symbolic-ref": "", "stash": ""}
        head = self._git("rev-parse", "--verify", "HEAD")
        state["HEAD"] = head.stdout.strip()
        symbolic = self._git("symbolic-ref", "-q", "HEAD")
        state["symbolic-ref"] = symbolic.stdout.strip()
        refs = self._git(
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/heads",
            "refs/remotes",
            "refs/tags",
        )
        for line in refs.stdout.splitlines():
            fields = line.strip().split(None, 1)
            if len(fields) == 2:
                state[fields[0]] = fields[1]
        stashes = self._git("stash", "list", "--format=%H")
        state["stash"] = "\n".join(
            line.strip() for line in stashes.stdout.splitlines() if line.strip()
        )
        return state

    def test_a_sibling_worktree_commit_is_not_a_difference(self):
        """A commit in ANOTHER worktree moves a shared ref, not this card's.

        ``refs/heads/*`` is one namespace for the whole repository, so the
        branch a sibling has checked out advances in this worktree's listing
        too. That is worktree isolation working as intended, so the narrowed
        probe must report no difference -- this is the bug card67 fixes.
        """
        self._init_repo()
        self._seed_commit()
        sibling = os.path.join(os.path.dirname(self.workdir), "sibling")
        self._git("worktree", "add", "-q", "-b", "lane", sibling)

        before = verify.git_state_snapshot(self.workdir)
        # The setup is real: the raw ref list does carry the sibling's branch...
        raw = self._git("for-each-ref", "--format=%(refname)", "refs/heads")
        self.assertIn("refs/heads/lane", raw.stdout)
        # ...but the narrowing knows it belongs to another checkout.
        self.assertEqual(
            verify._branches_checked_out_elsewhere(self.workdir),
            {"refs/heads/lane"},
        )
        self.assertNotIn("refs/heads/lane", before)

        with open(os.path.join(sibling, "work.txt"), "w") as handle:
            handle.write("work\n")
        self._git_in(sibling, "add", "work.txt")
        self._git_in(sibling, "commit", "-qm", "sibling work")

        after = verify.git_state_snapshot(self.workdir)
        self.assertEqual(verify.diff_snapshots(before, after), [])
        self.assertEqual(before, after)

    def test_own_worktree_history_moves_are_still_seen(self):
        """The narrowing keeps everything the card itself can move."""
        self._init_repo()
        self._seed_commit()

        # A commit of its own.
        before = verify.git_state_snapshot(self.workdir)
        self._git("commit", "--allow-empty", "-qm", "mine")
        self.assertIn(
            "HEAD", verify.diff_snapshots(before, verify.git_state_snapshot(self.workdir))
        )

        # A branch of its own (checked out in THIS worktree, so not excluded).
        before = verify.git_state_snapshot(self.workdir)
        self._git("checkout", "-q", "-b", "mine-branch")
        changed = verify.diff_snapshots(before, verify.git_state_snapshot(self.workdir))
        self.assertIn("refs/heads/mine-branch", changed)
        self.assertIn("symbolic-ref", changed)

        # A tag of its own.
        before = verify.git_state_snapshot(self.workdir)
        self._git("tag", "mine-tag")
        self.assertIn(
            "refs/tags/mine-tag",
            verify.diff_snapshots(before, verify.git_state_snapshot(self.workdir)),
        )

        # A stash of its own.
        tracked = os.path.join(self.workdir, "tracked.txt")
        with open(tracked, "w") as handle:
            handle.write("seed\n")
        self._git("add", "tracked.txt")
        self._git("commit", "-qm", "seed tracked")
        with open(tracked, "w") as handle:
            handle.write("changed\n")
        before = verify.git_state_snapshot(self.workdir)
        self._git("stash", "push", "-qm", "mine")
        self.assertIn(
            "stash",
            verify.diff_snapshots(before, verify.git_state_snapshot(self.workdir)),
        )

    def test_a_branch_only_a_sibling_holds_is_excluded(self):
        """Exclusion is keyed on the ref's branch, not its name shape."""
        self._init_repo()
        self._seed_commit()
        # A branch nobody has checked out stays in the snapshot...
        self._git("branch", "loose")
        snapshot = verify.git_state_snapshot(self.workdir)
        self.assertIn("refs/heads/loose", snapshot)
        self.assertEqual(verify._branches_checked_out_elsewhere(self.workdir), set())

        # ...the moment a sibling checks it out, it is another worktree's and
        # drops out; the current worktree's own branch stays in either way.
        sibling = os.path.join(os.path.dirname(self.workdir), "sibling")
        self._git("worktree", "add", sibling, "loose")
        self.assertEqual(
            verify._branches_checked_out_elsewhere(self.workdir),
            {"refs/heads/loose"},
        )
        self.assertNotIn("refs/heads/loose", verify.git_state_snapshot(self.workdir))
        current = self._git("symbolic-ref", "--short", "HEAD").stdout.strip()
        self.assertIn(f"refs/heads/{current}", verify.git_state_snapshot(self.workdir))

    def test_no_other_worktree_matches_the_legacy_snapshot(self):
        """With no sibling the exclusion set is empty and the snapshot is
        byte-for-byte the old (pre-narrowing) probe."""
        self._init_repo()
        self._seed_commit()
        self._git("branch", "extra")
        self._git("tag", "v1")

        self.assertEqual(verify._branches_checked_out_elsewhere(self.workdir), set())
        self.assertEqual(verify.git_state_snapshot(self.workdir), self._legacy_snapshot())


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
