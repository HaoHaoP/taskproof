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

from taskproof import dispatch, storage
from taskproof.api import server
from taskproof.models import Task


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ws = os.path.join(cls._tmp.name, "workspace")
        dispatch.prepare_workspace(cls.ws)

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

    def test_projects(self):
        status, body = self._request("/api/projects")
        self.assertEqual(status, 200)
        self.assertIsInstance(body["projects"], list)
        self.assertTrue(body["projects"])
        self.assertIn("id", body["projects"][0])

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


if __name__ == "__main__":
    unittest.main()
