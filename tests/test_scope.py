"""Scope resolution contract (`registry.resolve_scope`).

Pinned here:
  * cwd inside a registered repo (root or any descendant) locks that project,
  * nested projects resolve by LONGEST path match,
  * symlinks are resolved before comparing (macOS /tmp vs /private/tmp),
  * cwd outside every project falls back to "all",
  * priority is `--project` > `--all` > cwd, and `--project` wins when both
    flags are given.
"""

import os
import unittest
import tempfile

from taskproof import registry
from taskproof.models import Project, Taskgroup


def make_registry(taskgroups):
    """A registry whose every taskgroup is the sole lane of its own project."""
    projects = {}
    for taskgroup in taskgroups:
        projects.setdefault(
            taskgroup.project, Project(id=taskgroup.project, path=taskgroup.path)
        )
    return registry.Registry(list(projects.values()), list(taskgroups), {})


def project(pid, path, **kwargs):
    """A single-lane project: lane id == project id (the compat fallback)."""
    aliases = kwargs.pop("aliases", [])
    return Taskgroup(id=pid, project=pid, path=path, aliases=aliases, **kwargs)


class ResolveScopeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # realpath: on macOS the temp dir sits under /var, itself a symlink.
        self.root = os.path.realpath(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _mkdir(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    # -- cwd inference -----------------------------------------------------

    def test_cwd_at_project_root_locks_project(self):
        app = self._mkdir("app")
        reg = make_registry([project("app", app)])
        scope, source = registry.resolve_scope(reg, cwd=app)
        self.assertEqual(scope, "app")
        self.assertEqual(source, "来自 cwd")

    def test_cwd_in_multi_level_subdir_locks_project(self):
        app = self._mkdir("app")
        deep = self._mkdir("app", "src", "pkg", "deep")
        reg = make_registry([project("app", app)])
        scope, source = registry.resolve_scope(reg, cwd=deep)
        self.assertEqual(scope, "app")
        self.assertEqual(source, "来自 cwd")

    def test_nested_projects_take_longest_match(self):
        outer = self._mkdir("outer")
        inner = self._mkdir("outer", "inner")
        child = self._mkdir("outer", "inner", "sub")
        reg = make_registry([project("outer", outer), project("inner", inner)])

        # deep inside the child: the child wins, not the parent repo
        self.assertEqual(registry.resolve_scope(reg, cwd=child)[0], "inner")
        # inside the parent but outside the child: the parent wins
        self.assertEqual(registry.resolve_scope(reg, cwd=outer)[0], "outer")

    def test_symlinked_path_matches_real_path(self):
        real = self._mkdir("real")
        link = os.path.join(self.root, "link")
        os.symlink(real, link)

        # registered as the real path, invoked through the symlink
        reg_real = make_registry([project("real", real)])
        self.assertEqual(registry.resolve_scope(reg_real, cwd=link)[0], "real")

        # registered as the symlink path, invoked at the real path
        reg_link = make_registry([project("link", link)])
        self.assertEqual(registry.resolve_scope(reg_link, cwd=real)[0], "link")

    def test_cwd_outside_every_project_is_all(self):
        self._mkdir("app")
        outside = self._mkdir("elsewhere")
        reg = make_registry([project("app", os.path.join(self.root, "app"))])
        scope, source = registry.resolve_scope(reg, cwd=outside)
        self.assertIsNone(scope)
        self.assertEqual(source, "cwd 不在任何已登记仓库内")

    def test_cwd_defaults_to_os_getcwd(self):
        app = self._mkdir("app")
        reg = make_registry([project("app", app)])
        previous = os.getcwd()
        os.chdir(app)
        try:
            self.assertEqual(registry.resolve_scope(reg)[0], "app")
        finally:
            os.chdir(previous)

    # -- explicit overrides ------------------------------------------------

    def test_project_flag_overrides_cwd(self):
        a = self._mkdir("a")
        b = self._mkdir("b")
        reg = make_registry([project("a", a), project("b", b)])
        scope, source = registry.resolve_scope(reg, explicit_project="b", cwd=a)
        self.assertEqual(scope, "b")
        self.assertEqual(source, "来自 --project")

    def test_all_flag_overrides_cwd(self):
        a = self._mkdir("a")
        reg = make_registry([project("a", a)])
        scope, source = registry.resolve_scope(reg, force_all=True, cwd=a)
        self.assertIsNone(scope)
        self.assertEqual(source, "来自 --all")

    def test_project_wins_over_all_when_both_given(self):
        a = self._mkdir("a")
        reg = make_registry([project("a", a)])
        scope, source = registry.resolve_scope(
            reg, explicit_project="a", force_all=True, cwd=a
        )
        self.assertEqual(scope, "a")
        self.assertEqual(source, "来自 --project")

    def test_explicit_alias_resolves_to_canonical_id(self):
        a = self._mkdir("a")
        reg = make_registry([project("app", a, aliases=["a"])])
        scope, source = registry.resolve_scope(reg, explicit_project="a")
        self.assertEqual(scope, "app")
        self.assertEqual(source, "来自 --project")

    def test_no_registry_still_honours_explicit_project(self):
        # A workspace with no registry must not explode; cwd falls back to all.
        scope, source = registry.resolve_scope(None, explicit_project="ghost")
        self.assertEqual(scope, "ghost")
        self.assertEqual(source, "来自 --project")
        self.assertIsNone(registry.resolve_scope(None, cwd=self.root)[0])


class MultiLaneScopeTest(unittest.TestCase):
    """A project id resolves only when it has exactly one lane; cwd picks the
    deepest lane path and refuses a tie."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _mkdir(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def _reg(self, taskgroups):
        projects = {}
        for tg in taskgroups:
            projects.setdefault(tg.project, Project(id=tg.project, path=tg.path))
        return registry.Registry(list(projects.values()), list(taskgroups), {})

    def test_single_lane_project_id_resolves_to_that_lane(self):
        app = self._mkdir("app")
        tg = Taskgroup(id="app-main", project="app", path=app)
        reg = self._reg([tg])
        self.assertEqual(reg.by_id("app").id, "app-main")

    def test_multi_lane_project_id_is_refused_with_candidates(self):
        app = self._mkdir("app")
        reg = self._reg(
            [
                Taskgroup(id="app-main", project="app", path=app),
                Taskgroup(id="app-docs", project="app", path=app),
            ]
        )
        with self.assertRaises(registry.RegistryError) as ctx:
            reg.by_id("app")
        message = str(ctx.exception)
        self.assertIn("app-main", message)
        self.assertIn("app-docs", message)

    def test_cwd_picks_the_deepest_lane_path(self):
        app = self._mkdir("app")
        site = self._mkdir("app", "site")
        reg = self._reg(
            [
                Taskgroup(id="app-main", project="app", path=app),
                Taskgroup(id="app-docs", project="app", path=site),
            ]
        )
        self.assertEqual(registry.resolve_scope(reg, cwd=site)[0], "app-docs")
        self.assertEqual(registry.resolve_scope(reg, cwd=app)[0], "app-main")

    def test_cwd_tie_is_refused_with_candidates(self):
        app = self._mkdir("app")
        reg = self._reg(
            [
                Taskgroup(id="lane-a", project="app", path=app),
                Taskgroup(id="lane-b", project="app", path=app),
            ]
        )
        with self.assertRaises(registry.RegistryError) as ctx:
            registry.resolve_scope(reg, cwd=app)
        message = str(ctx.exception)
        self.assertIn("lane-a", message)

    def test_project_path_resolves_only_when_lane_is_unique(self):
        # A project path may differ from every lane path (lanes live in
        # subdirectories). Resolution must fall through to the project and then
        # hand back the one lane -- never a bare `Project` object.
        app = self._mkdir("app")
        main = self._mkdir("app", "main")
        reg = registry.Registry(
            [Project(id="app", path=app)],
            [Taskgroup(id="app-main", project="app", path=main)],
            {},
        )
        self.assertEqual(reg.by_id(app).id, "app-main")

    def test_multi_lane_project_path_is_refused_with_candidates(self):
        app = self._mkdir("app")
        main = self._mkdir("app", "main")
        docs = self._mkdir("app", "docs")
        reg = registry.Registry(
            [Project(id="app", path=app)],
            [
                Taskgroup(id="app-main", project="app", path=main),
                Taskgroup(id="app-docs", project="app", path=docs),
            ],
            {},
        )
        with self.assertRaises(registry.RegistryError) as ctx:
            reg.by_id(app)
        message = str(ctx.exception)
        self.assertIn("app-main", message)
        self.assertIn("app-docs", message)

    def test_bare_project_path_resolves_to_nothing(self):
        # A project with no lanes is a filter-only unit: its path resolves to
        # no taskgroup, never a bare `Project`.
        app = self._mkdir("app")
        reg = registry.Registry([Project(id="app", path=app)], [], {})
        self.assertIsNone(reg.by_id(app))


if __name__ == "__main__":
    unittest.main()
