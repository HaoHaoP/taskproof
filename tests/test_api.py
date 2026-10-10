"""Local REST API contract: read-only, loopback-only, always JSON.

A real server is bound to an ephemeral port and exercised with `urllib`; only
127.0.0.1 is contacted. Nothing reaches the network.
"""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from taskproof import concurrency, dispatch, registry, storage
from taskproof.api import server
from taskproof.models import Task


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ws = os.path.join(cls._tmp.name, "workspace")
        dispatch.prepare_workspace(cls.ws)

        # The project the task below belongs to, written explicitly. This used to
        # be implicit: a fresh workspace held a placeholder project, so the
        # `/api/projects` assertion passed against a repository that did not
        # exist. Once the placeholder went away the assertion failed -- which is
        # the assertion doing its job for the first time.
        with open(registry.workspace_registry_path(cls.ws), "w", encoding="utf-8") as fh:
            fh.write(
                "[[project]]\n"
                'id = "proj"\n'
                f'path = "{cls._tmp.name}"\n'
                'group = "proj"\n'
                'verify = "exit 0"\n'
                'verify_kind = "check"\n'
            )

        conn = storage.connect(storage.db_path(cls.ws))
        try:
            storage.migrate(conn)
            storage.insert_task(
                conn,
                Task(
                    id="t-1",
                    project="proj",
                    group="proj",
                    brief="hello",
                    status="done",
                    verify_cmd="exit 0",
                    verify_exit=0,
                    created_at=storage.now_iso(),
                    started_at=storage.now_iso(),
                    finished_at=storage.now_iso(),
                ),
            )
            storage.append_event(conn, "t-1", "done", {"ok": True})
        finally:
            conn.close()

        cls.httpd = server.make_server(cls.ws, port=0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()

    # -- helpers ----------------------------------------------------------

    def _request(self, path, *, method="GET"):
        url = f"http://127.0.0.1:{self.port}{path}"
        request = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    # -- tests ------------------------------------------------------------

    def test_binds_to_loopback_only(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    def test_health(self):
        status, body = self._request("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["version"])

    def test_summary(self):
        status, body = self._request("/api/summary")
        self.assertEqual(status, 200)
        self.assertEqual(body["summary"]["done"], 1)
        self.assertIn("failed", body["summary"])

    def test_health_exposes_the_effective_cap_and_source(self):
        status, body = self._request("/api/health")
        self.assertEqual(status, 200)
        cap = body["concurrency"]
        self.assertEqual(set(cap), {"value", "source", "detail"})
        # No `concurrency` key in this workspace's registry -> auto.
        self.assertEqual(cap["source"], "auto")
        self.assertEqual(cap["value"], concurrency.detect())

    def test_summary_exposes_the_effective_cap_and_source(self):
        status, body = self._request("/api/summary")
        self.assertEqual(status, 200)
        self.assertEqual(set(body["concurrency"]), {"value", "source", "detail"})
        self.assertEqual(body["concurrency"]["source"], "auto")

    def test_projects(self):
        status, body = self._request("/api/projects")
        self.assertEqual(status, 200)
        self.assertIsInstance(body["projects"], list)
        self.assertEqual([p["id"] for p in body["projects"]], ["proj"])
        # One row per lane: the historical keys are all present, plus the
        # owning `project` id. This pins the "shape unchanged, one added field"
        # contract the dashboard's `?project=` filter relies on.
        row = body["projects"][0]
        self.assertEqual(row["project"], "proj")
        self.assertEqual(
            set(row),
            {
                "id", "project", "path", "group", "aliases", "verify",
                "verify_kind", "forbidden_paths", "result_schema",
                "auto_registered", "probe", "probe_exit",
                "tasks", "in_progress", "failed", "last_activity",
            },
        )

    def test_tasks_list_and_filters(self):
        status, body = self._request("/api/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["tasks"][0]["id"], "t-1")

        status, body = self._request("/api/tasks?status=done")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["tasks"]), 1)

        status, body = self._request("/api/tasks?status=failed")
        self.assertEqual(status, 200)
        self.assertEqual(body["tasks"], [])

    def test_task_detail_and_events(self):
        status, body = self._request("/api/tasks/t-1")
        self.assertEqual(status, 200)
        self.assertEqual(body["task"]["id"], "t-1")
        self.assertTrue(body["events"])

        status, body = self._request("/api/tasks/t-1/events")
        self.assertEqual(status, 200)
        self.assertEqual(body["task_id"], "t-1")
        self.assertEqual(body["events"][-1]["event"], "done")

    def test_unknown_task_is_404(self):
        status, body = self._request("/api/tasks/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_unknown_path_is_404(self):
        status, body = self._request("/api/does-not-exist")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_write_verbs_are_404_not_405(self):
        # The write surface is gone, so a write verb is no longer a
        # "method not allowed": the verb/path pair is simply unrouted.
        for method in ("POST", "PUT", "DELETE"):
            status, body = self._request("/api/tasks", method=method)
            self.assertEqual(status, 404, method)
            self.assertIn("error", body)

    def test_old_write_paths_are_404(self):
        # Two of the write endpoints that used to exist are gone outright:
        # no route matches, so they answer 404. Never 403 -- there is no gate
        # left to forbid anything.
        for method, path in (
            ("POST", "/api/projects"),
            ("POST", "/api/tasks/t-1/cancel"),
        ):
            status, body = self._request(path, method=method)
            self.assertEqual(status, 404, (method, path))
            self.assertIn("error", body)


class ProjectsByProjectTest(unittest.TestCase):
    """The grouped `?by=project` view, layered on top of the lane-shaped one.

    Two lanes share one project ("app"); a flat legacy `[[project]]` block is a
    project plus a same-named lane ("solo"). The old `/api/projects` shape must
    stay one row per lane -- the desktop keys its `?project=` filter off the row
    id -- so the grouped view is a *new* `?by=project` branch, never a rewrite.
    """

    LEGACY_ROW_KEYS = {
        "id", "project", "path", "group", "aliases", "verify", "verify_kind",
        "forbidden_paths", "result_schema", "auto_registered", "probe",
        "probe_exit", "tasks", "in_progress", "failed", "last_activity",
    }
    SUMMARY_KEYS = {
        "running", "verifying", "done", "failed", "blocked", "timeout",
        "cancelled",
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self._tmp.name, "workspace")
        dispatch.prepare_workspace(self.ws)
        app = os.path.join(self._tmp.name, "app")
        solo = os.path.join(self._tmp.name, "solo")
        os.makedirs(app)
        os.makedirs(solo)
        with open(registry.workspace_registry_path(self.ws), "w", encoding="utf-8") as fh:
            fh.write(
                "[defaults]\nconcurrency = 3\n\n"
                '[[project]]\nid = "app"\n'
                f'path = "{app}"\naliases = ["the-app"]\n\n'
                '[[taskgroup]]\nid = "app-core"\nproject = "app"\n'
                f'path = "{app}"\nverify = "exit 0"\nverify_kind = "check"\n\n'
                '[[taskgroup]]\nid = "app-web"\nproject = "app"\n'
                f'path = "{app}"\nverify = "exit 0"\nverify_kind = "check"\n\n'
                '[[project]]\nid = "solo"\n'
                f'path = "{solo}"\ngroup = "solo"\n'
                'verify = "exit 0"\nverify_kind = "check"\n'
            )
        conn = storage.connect(storage.db_path(self.ws))
        try:
            storage.migrate(conn)
            for task_id, lane, status in (
                ("t-core", "app-core", "done"),
                ("t-web", "app-web", "failed"),
                ("t-solo", "solo", "running"),
            ):
                storage.insert_task(
                    conn,
                    Task(
                        id=task_id,
                        project=lane,
                        group=lane,
                        brief="x",
                        status=status,
                        created_at=storage.now_iso(),
                    ),
                )
        finally:
            conn.close()
        self.httpd = server.make_server(self.ws, port=0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def _request(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_projects_without_by_stays_one_row_per_lane(self):
        status, body = self._request("/api/projects")
        self.assertEqual(status, 200)
        # The top-level wrapper is unchanged: no new keys, no renamed list.
        self.assertEqual(set(body), {"projects"})
        # One row per lane, in registry load order (legacy lanes first).
        self.assertEqual(
            [row["id"] for row in body["projects"]],
            ["solo", "app-core", "app-web"],
        )
        for row in body["projects"]:
            self.assertEqual(set(row), self.LEGACY_ROW_KEYS)
        by_id = {row["id"]: row for row in body["projects"]}
        self.assertEqual(by_id["app-core"]["project"], "app")
        self.assertEqual(by_id["solo"]["project"], "solo")

    def test_by_project_groups_lanes_under_one_row(self):
        status, body = self._request("/api/projects?by=project")
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"projects"})
        rows = {row["id"]: row for row in body["projects"]}
        self.assertEqual(set(rows), {"app", "solo"})
        app = rows["app"]
        self.assertEqual(
            set(app), {"id", "path", "aliases", "taskgroups", "summary"}
        )
        self.assertEqual([tg["id"] for tg in app["taskgroups"]], ["app-core", "app-web"])
        self.assertEqual(app["aliases"], ["the-app"])
        self.assertEqual(set(app["summary"]), self.SUMMARY_KEYS)
        self.assertEqual(app["summary"]["done"], 1)
        self.assertEqual(app["summary"]["failed"], 1)
        self.assertEqual(app["summary"]["running"], 0)
        # The legacy project collapses to exactly its same-named lane.
        self.assertEqual(
            [tg["id"] for tg in rows["solo"]["taskgroups"]], ["solo"]
        )

    def test_tasks_filter_accepts_project_and_lane_ids(self):
        # A project id returns every lane it owns...
        status, body = self._request("/api/tasks?project=app")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 2)
        # ...a lane id keeps its old single-lane meaning...
        status, body = self._request("/api/tasks?project=app-core")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        # ...and a legacy project id is both layers at once.
        status, body = self._request("/api/tasks?project=solo")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        # An id neither layer knows is an empty set, never a 500.
        status, body = self._request("/api/tasks?project=ghost")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 0)


class ListeningLineTest(unittest.TestCase):
    """A parent that spawns `api --port 0` learns the port from this one line.

    If the line carried the requested port (0) instead of the bound one, the
    desktop app would have nothing to connect to.
    """

    def test_line_carries_the_bound_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "workspace")
            dispatch.prepare_workspace(ws)
            httpd = server.make_server(ws, port=0)
            try:
                bound = httpd.server_address[1]
                self.assertNotEqual(bound, 0, "port=0 must resolve to a free port")
                line = server.listening_line(httpd)
                self.assertIn(f"127.0.0.1:{bound}", line)
                self.assertNotIn(":0", line)
            finally:
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
