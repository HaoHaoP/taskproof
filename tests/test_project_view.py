"""Project-dimension views: `tasks` grouping, `projects` overview, the board.

The invariants pinned here:
  * every `tasks` output carries a scope label (cwd / --project / --all),
  * the "全部" scope groups by project and shows a PROJECT column,
  * `project_overview()` numbers are derived from the same rows `list_tasks`
    returns (they must agree),
  * the board is grouped into one `<section>` per project with tasks, ordered
    by most recent activity, still zero `<script>`, still escaping user text,
  * serve mode filters by `?project=` (unknown ids 404).
"""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from taskproof import cli, dispatch, storage
from taskproof.board import render
from taskproof.models import Task


def _registry_toml(entries):
    lines = ["[defaults]", "concurrency = 3", "timeout = 60", ""]
    for entry in entries:
        lines += [
            "[[project]]",
            f'id = "{entry["id"]}"',
            f'path = "{entry["path"]}"',
            f'group = "{entry["id"]}"',
        ]
        if entry.get("verify"):
            lines.append(f'verify = "{entry["verify"]}"')
            lines.append('verify_kind = "check"')
        else:
            lines.append('verify_kind = "none"')
        lines.append("")
    return "\n".join(lines) + "\n"


@contextlib.contextmanager
def chdir(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class ProjectViewBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.ws = os.path.join(self.root, "workspace")
        self.alpha = os.path.join(self.root, "alpha")
        self.beta = os.path.join(self.root, "beta")
        self.loose = os.path.join(self.root, "loose")
        for path in (self.alpha, self.beta, self.loose):
            os.makedirs(path, exist_ok=True)
        dispatch.prepare_workspace(self.ws)
        with open(os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8") as fh:
            fh.write(
                _registry_toml(
                    [
                        {"id": "alpha", "path": self.alpha, "verify": "exit 0"},
                        {"id": "beta", "path": self.beta},
                    ]
                )
            )

    def tearDown(self):
        self._tmp.cleanup()

    def _connect(self):
        conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(conn)
        return conn

    def insert(self, task_id, project, *, status="done", brief="x",
               created_at="2026-10-01T10:00:00+08:00"):
        conn = self._connect()
        try:
            storage.insert_task(
                conn,
                Task(
                    id=task_id,
                    project=project,
                    group=project,
                    brief=brief,
                    status=status,
                    created_at=created_at,
                ),
            )
        finally:
            conn.close()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--workspace", self.ws, *argv])
        return code, out.getvalue()

    def _seed_tasks(self):
        self.insert("t-a1", "alpha", created_at="2026-10-01T10:00:00+08:00")
        self.insert("t-a2", "alpha", created_at="2026-10-04T10:00:00+08:00")
        self.insert("t-b1", "beta", created_at="2026-10-03T10:00:00+08:00")


# --------------------------------------------------------------------------
# projects overview
# --------------------------------------------------------------------------

class ProjectOverviewTest(ProjectViewBase):
    def test_overview_counts_match_list_tasks(self):
        self.insert("t-a1", "alpha", status="queued")
        self.insert("t-a2", "alpha", status="failed")
        self.insert("t-a3", "alpha", status="done")
        self.insert("t-b1", "beta", status="running")
        self.insert("t-b2", "beta", status="failed")

        conn = self._connect()
        try:
            overview = storage.project_overview(conn)
            by_id = {row["project"]: row for row in overview}
            for row in overview:
                tasks = storage.list_tasks(conn, project=row["project"], limit=1000)
                self.assertEqual(row["total"], len(tasks), row["project"])
                self.assertEqual(
                    row["in_progress"],
                    sum(t["status"] in ("queued", "running", "verifying") for t in tasks),
                )
                self.assertEqual(
                    row["failed"], sum(t["status"] == "failed" for t in tasks)
                )
            # Every task in the DB is accounted for by exactly one project row.
            self.assertEqual(
                sum(r["total"] for r in overview),
                len(storage.list_tasks(conn, limit=1000)),
            )
        finally:
            conn.close()

        self.assertEqual(by_id["alpha"]["total"], 3)
        self.assertEqual(by_id["alpha"]["in_progress"], 1)  # queued
        self.assertEqual(by_id["alpha"]["failed"], 1)
        self.assertEqual(by_id["beta"]["in_progress"], 1)  # running
        self.assertEqual(by_id["beta"]["failed"], 1)

    def test_projects_command_reports_stats_and_config(self):
        self._seed_tasks()
        code, out = self.run_cli("--json", "projects")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        by_id = {p["id"]: p for p in payload["projects"]}
        self.assertEqual(by_id["alpha"]["tasks"], 2)
        self.assertEqual(by_id["beta"]["tasks"], 1)
        self.assertEqual(by_id["alpha"]["last_activity"], "2026-10-04T10:00:00+08:00")
        # Registry configuration is still visible.
        self.assertEqual(by_id["alpha"]["path"], self.alpha)
        self.assertEqual(by_id["alpha"]["verify"], "exit 0")
        # No-task project shows an em dash for activity in the human view.
        code, human = self.run_cli("projects")
        self.assertEqual(code, 0)
        self.assertIn("alpha", human)
        self.assertIn("LAST ACTIVITY", human)


# --------------------------------------------------------------------------
# tasks: scope labels + grouping
# --------------------------------------------------------------------------

class TasksScopeTest(ProjectViewBase):
    def test_scope_label_from_cwd_project_root(self):
        self._seed_tasks()
        with chdir(self.alpha):
            code, out = self.run_cli("tasks")
        self.assertEqual(code, 0)
        self.assertIn("当前项目: alpha（来自 cwd）", out)
        self.assertIn("t-a1", out)
        self.assertNotIn("t-b1", out)  # beta is out of scope
        self.assertNotIn("PROJECT", out)  # single-project view drops the column

    def test_scope_label_from_cwd_subdir(self):
        self._seed_tasks()
        deep = os.path.join(self.alpha, "src", "deep")
        os.makedirs(deep, exist_ok=True)
        with chdir(deep):
            code, out = self.run_cli("tasks")
        self.assertEqual(code, 0)
        self.assertIn("当前项目: alpha（来自 cwd）", out)

    def test_scope_label_outside_any_project_groups_all(self):
        self._seed_tasks()
        with chdir(self.loose):
            code, out = self.run_cli("tasks")
        self.assertEqual(code, 0)
        self.assertIn("作用域: 全部 2 个项目（cwd 不在任何已登记仓库内）", out)
        # grouped: one header per project, and the PROJECT column is shown
        self.assertIn("# alpha (2 个任务)", out)
        self.assertIn("# beta (1 个任务)", out)
        self.assertIn("PROJECT", out)
        # groups ordered by most recent activity (alpha 10-04 before beta 10-03)
        self.assertLess(out.index("# alpha"), out.index("# beta"))
        # tasks within a group newest-first
        self.assertLess(out.index("t-a2"), out.index("t-a1"))

    def test_all_flag_overrides_cwd(self):
        self._seed_tasks()
        with chdir(self.alpha):
            code, out = self.run_cli("tasks", "--all")
        self.assertEqual(code, 0)
        self.assertIn("作用域: 全部 2 个项目（来自 --all）", out)
        self.assertIn("# beta (1 个任务)", out)
        self.assertIn("t-b1", out)

    def test_project_flag_overrides_cwd(self):
        self._seed_tasks()
        with chdir(self.alpha):
            code, out = self.run_cli("tasks", "--project", "beta")
        self.assertEqual(code, 0)
        self.assertIn("当前项目: beta（来自 --project）", out)
        self.assertIn("t-b1", out)
        self.assertNotIn("t-a1", out)

    def test_json_output_carries_scope(self):
        self._seed_tasks()
        with chdir(self.loose):
            code, out = self.run_cli("--json", "tasks")
        payload = json.loads(out)
        self.assertIsNone(payload["project"])
        self.assertEqual(payload["scope"], "cwd 不在任何已登记仓库内")
        self.assertEqual(payload["count"], 3)

        with chdir(self.alpha):
            code, out = self.run_cli("--json", "tasks")
        payload = json.loads(out)
        self.assertEqual(payload["project"], "alpha")
        self.assertEqual(payload["scope"], "来自 cwd")


# --------------------------------------------------------------------------
# board
# --------------------------------------------------------------------------

class BoardGroupingTest(ProjectViewBase):
    def test_sections_match_projects_with_tasks(self):
        self._seed_tasks()
        doc = render.render_board(self.ws)
        # beta has tasks; the registry's other projects do not exist here, but
        # even a registered project with zero tasks adds no section.
        self.assertEqual(doc.count('<section class="project-block"'), 2)

    def test_project_without_tasks_has_no_section(self):
        self.insert("t-a1", "alpha")
        doc = render.render_board(self.ws)
        self.assertEqual(doc.count('<section class="project-block"'), 1)
        self.assertNotIn('id="project-beta"', doc)

    def test_sections_ordered_by_recent_activity(self):
        self.insert("t-a1", "alpha", created_at="2026-10-01T10:00:00+08:00")
        self.insert("t-b1", "beta", created_at="2026-10-05T10:00:00+08:00")
        doc = render.render_board(self.ws)
        self.assertLess(doc.index('id="project-beta"'), doc.index('id="project-alpha"'))

    def test_board_has_zero_script_tags(self):
        self._seed_tasks()
        doc = render.render_board(self.ws)
        self.assertNotIn("<script", doc)

    def test_board_escapes_project_id_and_brief(self):
        payload = "<script>alert('xss')</script>"
        self.insert("t-x", payload, brief=f"fix {payload}")
        doc = render.render_board(self.ws)
        self.assertNotIn("<script", doc)
        self.assertIn("&lt;script&gt;", doc)

    def test_board_single_project_filter(self):
        self._seed_tasks()
        doc = render.render_board(self.ws, project="alpha")
        self.assertEqual(doc.count('<section class="project-block"'), 1)
        self.assertIn("t-a1", doc)
        self.assertNotIn("t-b1", doc)

    def test_board_unaffected_by_cwd(self):
        self._seed_tasks()
        with chdir(self.alpha):
            doc = render.render_board(self.ws)
        # Still the global grouped view: beta's section is present.
        self.assertIn('id="project-beta"', doc)


class BoardServeTest(ProjectViewBase):
    def setUp(self):
        super().setUp()
        self._seed_tasks()
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), cli.board_handler_class(self.ws)
        )
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._thread.join(timeout=5)
        super().tearDown()

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def test_project_query_filters_to_subset(self):
        status, body = self._get("/?project=alpha")
        self.assertEqual(status, 200)
        self.assertEqual(body.count('<section class="project-block"'), 1)
        self.assertIn("t-a1", body)
        self.assertNotIn("t-b1", body)
        self.assertIn("proj-link active", body)  # current project highlighted

    def test_all_query_returns_everything(self):
        for path in ("/", "/?project="):
            status, body = self._get(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(body.count('<section class="project-block"'), 2, path)
            self.assertIn("t-a1", body, path)
            self.assertIn("t-b1", body, path)

    def test_unknown_project_is_404(self):
        status, body = self._get("/?project=ghost")
        self.assertEqual(status, 404)
        self.assertIn("unknown project", body.lower())

    def test_links_are_zero_javascript(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertNotIn("<script", body)
        self.assertIn('href="?project=alpha"', body)
        self.assertIn("全部", body)


if __name__ == "__main__":
    unittest.main()
