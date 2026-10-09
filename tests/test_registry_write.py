"""Surgical registry writes: byte preservation, comment ownership, atomicity.

These go one level below the HTTP surface to pin the guarantee that matters
most: a write edits only the bytes it must, and an invalid candidate never
reaches the real file.
"""

import difflib
import hashlib
import os
import tempfile
import unittest

from taskproof import registry
from taskproof.errors import RegistryError


HANDWRITTEN = '''\
# taskproof registry -- hand written, keep every comment
#
# field reference: docs/REGISTRY.md

[defaults]
concurrency = 2   # tuned by hand

# alpha: a note that belongs to alpha
[[project]]
id = "alpha"
path = "/tmp/alpha"
group = "alpha"
aliases = ["a"]
verify = "exit 0"
verify_kind = "check"
note = "custom key load() drops"

# an upstream note separated by a blank line
# (a previous block's note, not beta's)

# beta: note directly above the block
[[project]]
id = "beta"
path = "/tmp/beta"
group = "beta"
verify = "exit 0"
verify_kind = "check"
'''


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "projects.toml")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(HANDWRITTEN)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        with open(self.path, "rb") as fh:
            return fh.read()

    def text(self):
        return self.read().decode("utf-8")

    def hash(self):
        return hashlib.sha256(self.read()).hexdigest()


class AppendTest(_Base):
    def test_append_preserves_every_existing_byte(self):
        before = self.read()
        registry.append_project(
            self.path,
            self.hash(),
            {"id": "gamma", "path": "/tmp/gamma", "group": "gamma"},
        )
        after = self.read()
        self.assertTrue(after.startswith(before), "existing bytes were rewritten")
        self.assertIn('id = "gamma"', after.decode("utf-8"))

    def test_append_is_readable_by_load(self):
        registry.append_project(
            self.path, self.hash(), {"id": "gamma", "path": "/tmp/gamma"}
        )
        reg = registry.load(self.path)
        self.assertEqual([p.id for p in reg.projects], ["alpha", "beta", "gamma"])


class UpdateTest(_Base):
    def test_update_touches_only_the_named_lines(self):
        before = self.text().splitlines(keepends=True)
        registry.update_project(
            self.path, "alpha", self.hash(), {"group": "renamed", "aliases": ["a", "aa"]}
        )
        after = self.text().splitlines(keepends=True)
        diff = [
            line
            for line in difflib.unified_diff(before, after, n=0)
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        self.assertEqual(
            sorted(diff),
            sorted(['-group = "alpha"\n', '+group = "renamed"\n',
                    '-aliases = ["a"]\n', '+aliases = ["a", "aa"]\n']),
        )

    def test_update_preserves_unknown_keys_and_comments(self):
        registry.update_project(self.path, "alpha", self.hash(), {"group": "x"})
        text = self.text()
        self.assertIn('note = "custom key load() drops"', text)
        self.assertIn("# alpha: a note that belongs to alpha", text)
        self.assertIn("concurrency = 2   # tuned by hand", text)

    def test_update_does_not_touch_the_next_project(self):
        marker = "# an upstream note"
        before = self.read()[self.text().index(marker):]
        registry.update_project(self.path, "alpha", self.hash(), {"group": "x"})
        after = self.read()[self.text().index(marker):]
        self.assertEqual(after, before)

    def test_update_stale_hash_is_a_conflict_and_does_not_write(self):
        stale = self.hash()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("# hand edit\n")
        current = self.read()
        with self.assertRaises(registry.RegistryConflictError) as ctx:
            registry.update_project(self.path, "alpha", stale, {"group": "x"})
        self.assertEqual(ctx.exception.current_hash, hashlib.sha256(current).hexdigest())
        self.assertEqual(self.read(), current)

    def test_update_unknown_id(self):
        with self.assertRaises(registry.RegistryNotFoundError):
            registry.update_project(self.path, "nope", self.hash(), {"group": "x"})

    def test_update_rejects_immutable_fields(self):
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.update_project(self.path, "alpha", self.hash(), {"id": "z"})
        self.assertEqual(self.read(), before)

    def test_invalid_candidate_never_replaces_the_file(self):
        # An empty group is refused by validation; the file must stay byte-equal.
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.update_project(self.path, "alpha", self.hash(), {"group": ""})
        self.assertEqual(self.read(), before)

    def test_result_schema_is_mutable(self):
        registry.update_project(
            self.path, "alpha", self.hash(), {"result_schema": "none"}
        )
        reg = registry.load(self.path)
        alpha = reg.by_id("alpha")
        self.assertEqual(alpha.result_schema, "none")


class DeleteTest(_Base):
    def test_delete_last_block_keeps_upstream_comment(self):
        registry.delete_project(self.path, "beta", self.hash())
        text = self.text()
        self.assertNotIn('id = "beta"', text)
        # Upstream note is blank-separated, so it belongs to the previous block.
        self.assertIn("# an upstream note separated by a blank line", text)

    def test_delete_first_block_keeps_next_projects_comments(self):
        registry.delete_project(self.path, "alpha", self.hash())
        text = self.text()
        self.assertNotIn('id = "alpha"', text)
        self.assertNotIn("# alpha: a note that belongs to alpha", text)
        self.assertIn("# an upstream note separated by a blank line", text)
        self.assertIn('id = "beta"', text)
        # Still parses, and only beta remains.
        self.assertEqual([p.id for p in registry.load(self.path).projects], ["beta"])

    def test_delete_removes_owned_comment(self):
        registry.delete_project(self.path, "beta", self.hash())
        text = self.text()
        self.assertNotIn("# beta: note directly above the block", text)
        self.assertIn("# an upstream note separated by a blank line", text)


class SetDefaultTest(_Base):
    """Card 42: `config` writes must not round-trip the file through TOML."""

    def test_swap_keeps_the_trailing_comment_and_spacing(self):
        registry.set_default(self.path, "concurrency", 7)
        text = self.text()
        self.assertIn("concurrency = 7   # tuned by hand", text)
        # Only the one line changed: the hand-written comment survived.
        self.assertNotIn("concurrency = 2", text)

    def test_only_the_value_changes_byte_for_byte(self):
        before = self.text().splitlines(keepends=True)
        registry.set_default(self.path, "concurrency", 7)
        after = self.text().splitlines(keepends=True)
        changed = [pair for pair in zip(before, after) if pair[0] != pair[1]]
        self.assertEqual(changed, [("concurrency = 2   # tuned by hand\n",
                                    "concurrency = 7   # tuned by hand\n")])
        self.assertEqual(len(before), len(after), "line count changed")

    def test_project_blocks_are_untouched(self):
        before = self.text()[self.text().index("# alpha"):]
        registry.set_default(self.path, "timeout", 60)
        after = self.text()[self.text().index("# alpha"):]
        self.assertEqual(after, before)

    def test_adds_a_key_the_table_lacks(self):
        # timeout is absent from HANDWRITTEN's [defaults]; it must be inserted
        # inside the table, not appended after the projects.
        registry.set_default(self.path, "timeout", 60)
        text = self.text()
        self.assertIn("timeout = 60", text)
        defaults_block = text.split("[[project]]", 1)[0]
        self.assertIn("timeout = 60", defaults_block)
        reg = registry.load(self.path)
        self.assertEqual(reg.timeout, 60)
        self.assertEqual([p.id for p in reg.projects], ["alpha", "beta"])

    def test_rejects_non_integer_without_writing(self):
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.set_default(self.path, "concurrency", "abc")
        self.assertEqual(self.read(), before)

    def test_rejects_below_one_without_writing(self):
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.set_default(self.path, "concurrency", 0)
        self.assertEqual(self.read(), before)

    def test_rejects_unknown_key(self):
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.set_default(self.path, "nope", 3)
        self.assertEqual(self.read(), before)

    def test_sets_both_defaults_and_keeps_the_file_valid(self):
        registry.set_default(self.path, "concurrency", 5)
        registry.set_default(self.path, "timeout", 90)
        reg = registry.load(self.path)
        self.assertEqual(reg.concurrency, 5)
        self.assertEqual(reg.timeout, 90)
        self.assertIn("# tuned by hand", self.text())


if __name__ == "__main__":
    unittest.main()
