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
        registry.append_taskgroup(
            self.path,
            self.hash(),
            {"id": "gamma", "path": "/tmp/gamma", "verify": "exit 0"},
        )
        after = self.read()
        self.assertTrue(after.startswith(before), "existing bytes were rewritten")
        text = after.decode("utf-8")
        self.assertIn("[[taskgroup]]", text)
        self.assertIn('id = "gamma"', text)

    def test_append_is_readable_by_load(self):
        registry.append_taskgroup(
            self.path, self.hash(), {"id": "gamma", "path": "/tmp/gamma"}
        )
        reg = registry.load(self.path)
        # gamma is self-contained: it stands up its own project.
        self.assertEqual([p.id for p in reg.projects], ["alpha", "beta", "gamma"])
        self.assertEqual(reg.require("gamma").project, "gamma")

    def test_append_stale_hash_is_a_conflict_and_does_not_write(self):
        stale = self.hash()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("# hand edit\n")
        current = self.read()
        with self.assertRaises(registry.RegistryConflictError) as ctx:
            registry.append_taskgroup(
                self.path, stale, {"id": "gamma", "path": "/tmp/gamma"}
            )
        self.assertEqual(ctx.exception.current_hash, hashlib.sha256(current).hexdigest())
        self.assertEqual(self.read(), current)


class UpdateTest(_Base):
    def test_update_touches_only_the_named_lines(self):
        before = self.text().splitlines(keepends=True)
        registry.update_project(
            self.path, "alpha", self.hash(),
            {"path": "/tmp/alpha2", "aliases": ["a", "aa"]},
        )
        after = self.text().splitlines(keepends=True)
        diff = [
            line
            for line in difflib.unified_diff(before, after, n=0)
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        self.assertEqual(
            sorted(diff),
            sorted(['-path = "/tmp/alpha"\n', '+path = "/tmp/alpha2"\n',
                    '-aliases = ["a"]\n', '+aliases = ["a", "aa"]\n']),
        )

    def test_update_preserves_unknown_keys_and_comments(self):
        registry.update_project(self.path, "alpha", self.hash(), {"aliases": ["x"]})
        text = self.text()
        self.assertIn('note = "custom key load() drops"', text)
        self.assertIn("# alpha: a note that belongs to alpha", text)
        self.assertIn("concurrency = 2   # tuned by hand", text)

    def test_update_does_not_touch_the_next_project(self):
        marker = "# an upstream note"
        before = self.read()[self.text().index(marker):]
        registry.update_project(self.path, "alpha", self.hash(), {"aliases": ["x"]})
        after = self.read()[self.text().index(marker):]
        self.assertEqual(after, before)

    def test_update_stale_hash_is_a_conflict_and_does_not_write(self):
        stale = self.hash()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("# hand edit\n")
        current = self.read()
        with self.assertRaises(registry.RegistryConflictError) as ctx:
            registry.update_project(self.path, "alpha", stale, {"aliases": ["x"]})
        self.assertEqual(ctx.exception.current_hash, hashlib.sha256(current).hexdigest())
        self.assertEqual(self.read(), current)

    def test_update_unknown_id(self):
        with self.assertRaises(registry.RegistryNotFoundError):
            registry.update_project(self.path, "nope", self.hash(), {"aliases": ["x"]})

    def test_update_rejects_immutable_fields(self):
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.update_project(self.path, "alpha", self.hash(), {"id": "z"})
        self.assertEqual(self.read(), before)

    def test_invalid_candidate_never_replaces_the_file(self):
        # A relative path is refused by validation; the file must stay equal.
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.update_project(self.path, "alpha", self.hash(), {"path": "rel"})
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


TWO_LAYER = '''\
# two-layer registry, keep every comment
[defaults]
concurrency = 2

# the repo itself
[[project]]
id = "api"
path = "/tmp/api"

# the primary lane (note that belongs to it)
[[taskgroup]]
id = "api-main"
project = "api"
verify = "make check"
verify_kind = "check"
note = "unknown key survives"

# a second lane
[[taskgroup]]
id = "api-docs"
project = "api"
path = "/tmp/api/site"
verify = "npm test"
verify_kind = "check"
'''


class TwoLayerWriteTest(_Base):
    """Surgical writes must work on both `[[project]]` and `[[taskgroup]]`."""

    def setUp(self):
        super().setUp()
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(TWO_LAYER)

    def test_append_taskgroup_under_existing_project(self):
        before = self.read()
        registry.append_taskgroup(
            self.path,
            self.hash(),
            {"id": "api-worker", "project": "api", "verify": "make lint"},
        )
        after = self.read()
        self.assertTrue(after.startswith(before))
        reg = registry.load(self.path)
        self.assertEqual(
            [t.id for t in reg.lanes_for("api")],
            ["api-main", "api-docs", "api-worker"],
        )
        # The new lane inherits the project's path.
        self.assertEqual(reg.require("api-worker").path, "/tmp/api")

    def test_update_taskgroup_touches_only_its_line(self):
        before = self.text().splitlines(keepends=True)
        registry.update_project(
            self.path, "api-main", self.hash(), {"verify": "make test"}
        )
        after = self.text().splitlines(keepends=True)
        diff = [
            line
            for line in difflib.unified_diff(before, after, n=0)
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        self.assertEqual(diff, ['-verify = "make check"\n', '+verify = "make test"\n'])
        self.assertIn('note = "unknown key survives"', self.text())
        self.assertIn("# the primary lane", self.text())

    def test_update_taskgroup_path_overrides_inheritance(self):
        registry.update_project(
            self.path, "api-docs", self.hash(), {"path": "/tmp/api/web"}
        )
        self.assertEqual(registry.load(self.path).require("api-docs").path, "/tmp/api/web")

    def test_update_project_block_does_not_touch_its_lanes(self):
        marker = "# the primary lane"
        before = self.read()[self.text().index(marker):]
        registry.update_project(self.path, "api", self.hash(), {"path": "/tmp/api2"})
        after = self.read()[self.text().index(marker):]
        self.assertEqual(after, before)
        self.assertEqual(registry.load(self.path).require("api-main").path, "/tmp/api2")

    def test_delete_taskgroup_keeps_project_and_neighbour(self):
        registry.delete_project(self.path, "api-main", self.hash())
        text = self.text()
        self.assertNotIn('id = "api-main"', text)
        self.assertNotIn("# the primary lane", text)
        self.assertIn('id = "api-docs"', text)
        self.assertIn('id = "api"', text)
        self.assertEqual([t.id for t in registry.load(self.path).taskgroups], ["api-docs"])

    def test_deleting_a_project_with_lanes_is_refused(self):
        # Removing the project would orphan its lanes, which `load` rejects; the
        # candidate never reaches disk.
        before = self.read()
        with self.assertRaises(RegistryError):
            registry.delete_project(self.path, "api", self.hash())
        self.assertEqual(self.read(), before)

    def test_delete_project_then_its_lanes(self):
        registry.delete_project(self.path, "api-main", self.hash())
        registry.delete_project(self.path, "api-docs", self.hash())
        registry.delete_project(self.path, "api", self.hash())
        text = self.text()
        self.assertNotIn("[[project]]", text)
        self.assertNotIn("[[taskgroup]]", text)


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
