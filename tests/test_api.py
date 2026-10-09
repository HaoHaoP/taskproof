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

    def test_non_get_is_405(self):
        for method in ("POST", "PUT", "DELETE"):
            status, body = self._request("/api/tasks", method=method)
            self.assertEqual(status, 405, method)
            self.assertIn("error", body)


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
