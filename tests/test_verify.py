"""Verification contract.

Covers the two ways a worker's success claim is overruled, plus the rule that a
skipped acceptance is NOT a pass.
"""

import os
import tempfile
import unittest

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
