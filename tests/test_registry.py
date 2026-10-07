"""Registry loading and resolution contract.

Pinned here:
  * the shipped example loads,
  * a project resolves by id, alias or absolute path,
  * malformed configuration is refused with RegistryError —
    relative paths, bad verify_kind, duplicate ids, missing file, bad TOML.
"""

import os
import tempfile
import textwrap
import unittest

from taskproof import registry
from taskproof.errors import RegistryError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(REPO_ROOT, "examples", "projects.example.toml")


class RegistryLoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, body, name="projects.toml"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(body))
        return path

    # -- happy path --------------------------------------------------------

    def test_load_example(self):
        reg = registry.load(EXAMPLE)
        self.assertEqual(reg.concurrency, 3)
        self.assertEqual(reg.timeout, 1800)
        self.assertEqual(
            {p.id for p in reg.projects}, {"my-app", "docs-site", "api-service"}
        )
        self.assertEqual(reg.source, EXAMPLE)

    def test_resolve_by_id_alias_and_path(self):
        reg = registry.load(EXAMPLE)
        self.assertEqual(reg.by_id("my-app").id, "my-app")
        self.assertEqual(reg.by_id("app").id, "my-app")  # alias
        self.assertEqual(reg.by_id("/absolute/path/to/my-app").id, "my-app")  # path
        self.assertIsNone(reg.by_id("does-not-exist"))

    def test_no_verify_command_means_kind_none(self):
        reg = registry.load(EXAMPLE)
        docs = reg.by_id("docs-site")
        self.assertIsNone(docs.verify)
        self.assertEqual(docs.verify_kind, "none")

    def test_group_defaults_when_omitted(self):
        path = self.write(
            """
            [[project]]
            id = "solo"
            path = "/tmp/solo"
            """
        )
        self.assertEqual(registry.load(path).by_id("solo").group, "default")

    # -- validation --------------------------------------------------------

    def test_missing_file_raises(self):
        with self.assertRaises(RegistryError):
            registry.load(os.path.join(self.tmp.name, "nope.toml"))

    def test_relative_path_is_rejected(self):
        path = self.write(
            """
            [[project]]
            id = "rel"
            path = "relative/dir"
            """
        )
        with self.assertRaises(RegistryError):
            registry.load(path)

    def test_invalid_verify_kind_is_rejected(self):
        path = self.write(
            """
            [[project]]
            id = "bad-kind"
            path = "/tmp/bad"
            verify = "make check"
            verify_kind = "trust-me"
            """
        )
        with self.assertRaises(RegistryError):
            registry.load(path)

    def test_duplicate_id_is_rejected(self):
        path = self.write(
            """
            [[project]]
            id = "dup"
            path = "/tmp/a"

            [[project]]
            id = "dup"
            path = "/tmp/b"
            """
        )
        with self.assertRaises(RegistryError):
            registry.load(path)

    def test_missing_id_is_rejected(self):
        path = self.write(
            """
            [[project]]
            path = "/tmp/no-id"
            """
        )
        with self.assertRaises(RegistryError):
            registry.load(path)

    def test_missing_path_is_rejected(self):
        path = self.write(
            """
            [[project]]
            id = "no-path"
            """
        )
        with self.assertRaises(RegistryError):
            registry.load(path)

    def test_toml_syntax_error_mentions_path_and_line(self):
        path = self.write(
            """
            [[project]
            id = "broken"
            """
        )
        with self.assertRaises(RegistryError) as ctx:
            registry.load(path)
        message = str(ctx.exception)
        self.assertIn(path, message)
        self.assertIn("line", message.lower())


if __name__ == "__main__":
    unittest.main()
