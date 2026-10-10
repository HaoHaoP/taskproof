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

    def test_lock_defaults_to_taskgroup_id(self):
        # The lock defaults to the lane id when `group` is not written.
        path = self.write(
            """
            [[taskgroup]]
            id = "solo"
            path = "/tmp/solo"
            """
        )
        self.assertEqual(registry.load(path).by_id("solo").group, "solo")

    def test_bare_project_has_no_lane(self):
        # A `[[project]]` with no lane field is a filter-only unit: nothing is
        # dispatchable until a lane hangs off it.
        path = self.write(
            """
            [[project]]
            id = "repo"
            path = "/tmp/repo"
            """
        )
        reg = registry.load(path)
        self.assertEqual([p.id for p in reg.projects], ["repo"])
        self.assertEqual(reg.taskgroups, [])
        self.assertIsNone(reg.by_id("repo"))

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


class TwoLayerTest(unittest.TestCase):
    """Project / taskgroup split, plus the zero-migration compat rule."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, body, name="projects.toml"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(body))
        return path

    def test_two_layer_parse_and_inheritance(self):
        path = self.write(
            """
            [[project]]
            id = "api"
            path = "/tmp/api"
            aliases = ["backend"]

            [[taskgroup]]
            id = "api-main"
            project = "api"
            verify = "make check"

            [[taskgroup]]
            id = "api-docs"
            project = "api"
            path = "/tmp/api/site"
            verify = "npm test"
            """
        )
        reg = registry.load(path)
        self.assertEqual([p.id for p in reg.projects], ["api"])
        self.assertEqual([t.id for t in reg.taskgroups], ["api-main", "api-docs"])
        main = reg.require("api-main")
        docs = reg.require("api-docs")
        # Path: inherited from the project, or overridden per lane.
        self.assertEqual(main.path, "/tmp/api")
        self.assertEqual(docs.path, "/tmp/api/site")
        # Project id is only usable when it has exactly one lane.
        with self.assertRaises(RegistryError) as ctx:
            reg.require("api")
        self.assertIn("api-main", str(ctx.exception))
        self.assertIn("api-docs", str(ctx.exception))

    def test_self_contained_taskgroup_stands_up_a_project(self):
        path = self.write(
            """
            [[taskgroup]]
            id = "solo"
            path = "/tmp/solo"
            verify_kind = "none"
            """
        )
        reg = registry.load(path)
        self.assertEqual([p.id for p in reg.projects], ["solo"])
        self.assertEqual(reg.require("solo").project, "solo")
        self.assertIsNone(reg.require("solo").verify)

    def test_taskgroup_group_can_share_a_lock(self):
        path = self.write(
            """
            [[taskgroup]]
            id = "one"
            path = "/tmp/one"
            group = "shared"

            [[taskgroup]]
            id = "two"
            path = "/tmp/two"
            group = "shared"
            """
        )
        reg = registry.load(path)
        one = reg.require("one")
        two = reg.require("two")
        self.assertEqual(one.group, "shared")
        self.assertEqual(two.group, "shared")

    def test_legacy_project_with_lane_field_is_project_plus_lane(self):
        # The zero-migration rule: a `[[project]]` carrying any lane field is
        # read as a project AND a same-named lane, so `require(<project id>)`
        # returns the lane.
        path = self.write(
            """
            [[project]]
            id = "legacy"
            path = "/tmp/legacy"
            group = "shared-lock"
            aliases = ["old"]
            verify = "exit 0"
            verify_kind = "check"
            """
        )
        reg = registry.load(path)
        self.assertEqual([p.id for p in reg.projects], ["legacy"])
        self.assertEqual([t.id for t in reg.taskgroups], ["legacy"])
        lane = reg.require("legacy")
        self.assertEqual(lane.verify, "exit 0")
        self.assertEqual(lane.verify_kind, "check")
        # The legacy lock name rides through the compatibility path unchanged.
        self.assertEqual(lane.group, "shared-lock")
        # Aliases ride on the project and still resolve.
        self.assertEqual(reg.require("old").id, "legacy")

    def test_legacy_shared_group_survives_require(self):
        # Regression pin: after load(), resolving both old entries by require()
        # must still leave them on the same lock.
        path = self.write(
            """
            [[project]]
            id = "one"
            path = "/tmp/one"
            group = "shared"
            verify = "exit 0"

            [[project]]
            id = "two"
            path = "/tmp/two"
            group = "shared"
            verify = "exit 0"
            """
        )
        reg = registry.load(path)
        self.assertEqual({t.id for t in reg.taskgroups}, {"one", "two"})
        one = reg.require("one")
        two = reg.require("two")
        self.assertEqual(one.group, "shared")
        self.assertEqual(two.group, "shared")
        self.assertEqual(one.group, two.group)

    def test_taskgroup_referencing_unknown_project_is_rejected(self):
        path = self.write(
            """
            [[taskgroup]]
            id = "orphan"
            project = "nowhere"
            path = "/tmp/orphan"
            """
        )
        with self.assertRaises(RegistryError) as ctx:
            registry.load(path)
        message = str(ctx.exception)
        self.assertIn("orphan", message)
        self.assertIn("nowhere", message)

    def test_taskgroup_without_path_or_project_is_rejected(self):
        path = self.write(
            """
            [[taskgroup]]
            id = "homeless"
            """
        )
        with self.assertRaises(RegistryError):
            registry.load(path)


class LegacyPinTest(unittest.TestCase):
    """The "pin": today's flat, legacy registry keeps loading unchanged.

    A real registry has ~22 `[[project]]` blocks -- several per repo, some
    sharing a lock via `group`, some pointing at a subdirectory or an
    out-of-repo clone. None of them may need editing: each block carrying a
    lane field reads as a same-named project *plus* a same-named lane, and
    every id / alias still resolves.
    """

    #: (id, repo, group, path-suffix, alias) -- fictional names only. Several
    #: rows share a repo (a second lane in the same checkout) and a lock.
    ROWS = [
        ("my-app", "my-app", "my-app-lock", "", None),
        ("my-app-tests", "my-app", "my-app-lock", "tests", None),
        ("my-app-docs", "my-app", "my-app-lock", "docs", None),
        ("my-app-web", "my-app", "my-app-lock", "web", None),
        ("my-app-api", "my-app", "my-app-lock", "api", None),
        ("my-app-cli", "my-app", "my-app-lock", "cli", None),
        ("my-app-infra", "my-app", "my-app-lock", "infra", None),
        ("docs-site", "docs-site", "docs-site", "", "site"),
        ("docs-site-guide", "docs-site", "docs-site", "guide", None),
        ("docs-site-api", "docs-site", "docs-site", "api", None),
        ("docs-site-blog", "docs-site", "docs-site", "blog", None),
        ("docs-site-clone-a", "docs-site", "docs-site", "../clones/a", None),
        ("docs-site-clone-b", "docs-site", "docs-site", "../clones/b", None),
        ("docs-site-clone-c", "docs-site", "docs-site", "../clones/c", None),
        ("docs-site-clone-d", "docs-site", "docs-site", "../clones/d", None),
        ("api-service", "api-service", "api-service", "", None),
        ("api-service-worker", "api-service", "api-service", "worker", None),
        ("api-service-admin", "api-service", "api-service", "admin", None),
        ("api-service-jobs", "api-service", "api-service", "jobs", None),
        ("data-pipeline", "data-pipeline", "data-pipeline", "", None),
        ("data-pipeline-etl", "data-pipeline", "data-pipeline", "etl", None),
        ("tools-cli", "tools-cli", "tools-cli", "", None),
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "repos")
        os.makedirs(self.root)
        blocks = []
        for entry_id, repo, group, suffix, alias in self.ROWS:
            path = os.path.normpath(os.path.join(self.root, repo, suffix))
            lines = [
                "[[project]]",
                f'id = "{entry_id}"',
                f'path = "{path}"',
                f'group = "{group}"',
            ]
            if alias:
                lines.append(f'aliases = ["{alias}"]')
            lines += ['verify = "exit 0"', 'verify_kind = "check"', ""]
            blocks.append("\n".join(lines))
        self.path = os.path.join(self.tmp.name, "projects.toml")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("[defaults]\nconcurrency = 3\ntimeout = 60\n\n")
            fh.write("\n".join(blocks))

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_legacy_row_loads_and_resolves(self):
        reg = registry.load(self.path)
        # Each block stands up its own project + a same-named lane.
        self.assertEqual(len(reg.projects), 22)
        self.assertEqual(len(reg.taskgroups), 22)
        for entry_id, _repo, group, _suffix, _alias in self.ROWS:
            lane = reg.require(entry_id)
            self.assertEqual(lane.id, entry_id)
            self.assertEqual(lane.project, entry_id)
            self.assertEqual(lane.group, group)
            self.assertEqual(lane.verify, "exit 0")

    def test_shared_legacy_group_still_parses(self):
        reg = registry.load(self.path)
        # The seven "my-app" lanes used to share one lock; they still load.
        shared = [t for t in reg.taskgroups if t.id.startswith("my-app")]
        self.assertEqual(len(shared), 7)
        for lane in shared:
            self.assertEqual(lane.group, "my-app-lock")

    def test_legacy_alias_rides_the_project(self):
        reg = registry.load(self.path)
        self.assertEqual(reg.require("site").id, "docs-site")

    def test_subdirectory_and_clone_paths_stay_distinct(self):
        reg = registry.load(self.path)
        self.assertEqual(
            reg.require("my-app-tests").path,
            os.path.join(self.root, "my-app", "tests"),
        )
        self.assertEqual(
            reg.require("docs-site-clone-a").path,
            os.path.join(self.root, "clones", "a"),
        )


if __name__ == "__main__":
    unittest.main()
