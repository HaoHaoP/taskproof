"""`GET /api/tasks/<id>/log` and the derived `files_changed_live` field.

Same style as `tests/test_api.py`: a real `server.make_server(ws, port=0)` bound
to loopback, driven with `urllib`. Nothing reaches the network. A couple of
tests shell out to `git` in a throwaway temp repo -- local, read-only from
taskproof's point of view (`git status --porcelain`).
"""

import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from taskproof import dispatch, storage
from taskproof.api import server
from taskproof.models import STATUS_DONE, STATUS_RUNNING, Task


def _git_available():
    try:
        subprocess.run(
            ["git", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


class ApiLogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ws = os.path.join(cls._tmp.name, "workspace")
        dispatch.prepare_workspace(cls.ws)
        cls.logs_dir = os.path.join(cls.ws, "logs")

        # A real git repo (two untracked files = two changed lines) and a plain
        # non-git directory, both used as a running task's `workdir`.
        cls.git_repo = os.path.join(cls._tmp.name, "git_repo")
        os.makedirs(cls.git_repo)
        if _git_available():
            subprocess.run(
                ["git", "init", "-q"],
                cwd=cls.git_repo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for name in ("a.txt", "b.txt"):
                path = os.path.join(cls.git_repo, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("x\n")

        cls.plain_dir = os.path.join(cls._tmp.name, "plain_dir")
        os.makedirs(cls.plain_dir)

        conn = storage.connect(storage.db_path(cls.ws))
        try:
            storage.migrate(conn)
            for i, task in enumerate(cls._tasks()):
                # Distinct created_at so the list order is deterministic.
                task.created_at = f"2026-01-01T00:00:{i:02d}+00:00"
                storage.insert_task(conn, task)
        finally:
            conn.close()

        cls.httpd = server.make_server(cls.ws, port=0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def _tasks(cls):
        base = dict(
            project="proj",
            group="proj",
            brief="hello",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
        )
        out = []
        for task_id in (
            "t-split",
            "t-tail",
            "t-chunk",
            "t-catchup",
            "t-empty",
            "t-nolog",
        ):
            out.append(Task(id=task_id, status="done", **base))
        # NOTE: this row is a *hand-built* fixture that scripts the helper's
        # contract only. It does NOT represent what a real running row carries
        # on disk -- card 55 fixed that (dispatch now writes `workdir` while the
        # task runs); `FilesChangedLiveEndToEndTest` is the real-run evidence.
        out.append(Task(id="t-live", status="running", workdir=cls.git_repo, **base))
        out.append(Task(id="t-nogit", status="running", workdir=cls.plain_dir, **base))
        out.append(Task(id="t-nowd", status="running", workdir=None, **base))
        return out

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()

    def setUp(self):
        # Process-wide cache: reset it so one test's probe cannot leak into the
        # next. (Within a single test the cache is exactly what we exercise.)
        server._LIVE_FILES_CACHE.clear()

    # -- helpers ----------------------------------------------------------

    def _request(self, path, *, method="GET"):
        url = f"http://127.0.0.1:{self.port}{path}"
        request = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _log_path(self, task_id):
        path = os.path.join(self.logs_dir, task_id + ".log")
        if os.path.exists(path):
            os.remove(path)
        return path

    def _write_log(self, task_id, data):
        path = self._log_path(task_id)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def _append_log(self, task_id, data):
        with open(os.path.join(self.logs_dir, task_id + ".log"), "ab") as fh:
            fh.write(data)

    def _task_from_list(self, task_id):
        status, body = self._request("/api/tasks")
        self.assertEqual(status, 200)
        for row in body["tasks"]:
            if row["id"] == task_id:
                return row
        self.fail(f"{task_id} not in /api/tasks")

    # -- 1. a chunk boundary must not split a multi-byte character ----------

    def test_chunk_boundary_never_splits_a_character(self):
        chunk = server.LOG_CHUNK_BYTES
        # The window [0, chunk) ends on the *lead* byte of a 3-byte char: the
        # response must drop it and hand back that char's first byte as `next`.
        head = b"A" * (chunk - 1)
        content = head + "中".encode("utf-8") + b"B" * 100
        self._write_log("t-split", content)

        status, first = self._request("/api/tasks/t-split/log?offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(first["offset"], 0)
        self.assertEqual(first["size"], len(content))
        self.assertEqual(first["omitted"], 0)
        # next fell back to the cut character's first byte, inside the window.
        self.assertEqual(first["next"], chunk - 1)
        self.assertLess(first["next"], chunk)
        self.assertNotIn("\ufffd", first["text"])

        status, second = self._request(
            f"/api/tasks/t-split/log?offset={first['next']}"
        )
        self.assertEqual(status, 200)
        self.assertTrue(second["eof"])

        combined = (first["text"] + second["text"]).encode("utf-8")
        self.assertEqual(combined, content)  # no duplication, no loss

    # -- 2. a bare request returns the tail, marked as omitted --------------

    def test_tail_request_reports_omitted_head(self):
        content = "".join(f"line {i:06d}\n" for i in range(12000)).encode("utf-8")
        self.assertGreater(len(content), server.LOG_TAIL_BYTES)
        self._write_log("t-tail", content)

        status, body = self._request("/api/tasks/t-tail/log")
        self.assertEqual(status, 200)
        self.assertGreater(body["offset"], 0)
        self.assertEqual(body["omitted"], body["offset"])
        self.assertLessEqual(len(body["text"].encode("utf-8")), server.LOG_TAIL_BYTES)
        returned = body["text"].encode("utf-8")
        self.assertEqual(returned, content[body["offset"]:body["next"]])
        self.assertEqual(body["eof"], body["next"] >= body["size"])

    # -- 3. one response never exceeds LOG_CHUNK_BYTES ----------------------

    def test_single_response_is_capped_at_the_chunk_size(self):
        content = b"x" * (server.LOG_CHUNK_BYTES + 5000)
        self._write_log("t-chunk", content)

        status, body = self._request("/api/tasks/t-chunk/log?offset=0")
        self.assertEqual(status, 200)
        returned = body["text"].encode("utf-8")
        self.assertLessEqual(len(returned), server.LOG_CHUNK_BYTES)
        self.assertEqual(len(returned), server.LOG_CHUNK_BYTES)
        self.assertEqual(body["offset"], 0)
        self.assertEqual(body["next"], server.LOG_CHUNK_BYTES)
        self.assertEqual(body["eof"], body["next"] >= body["size"])
        self.assertFalse(body["eof"])

    # -- 4. follow a file as it is written, resuming from `next` ------------

    def test_incremental_follow_reaches_eof_without_loss(self):
        content = "追踪测试".encode("utf-8")  # 12 bytes, 4 three-byte chars
        head = content[:4]  # ends one byte into the second char
        self._write_log("t-catchup", head)

        collected = ""
        offset = 0

        status, body = self._request(f"/api/tasks/t-catchup/log?offset={offset}")
        self.assertEqual(status, 200)
        collected += body["text"]
        offset = body["next"]

        # The writer finishes the character / the rest of the file.
        self._append_log("t-catchup", content[4:])

        status, body = self._request(f"/api/tasks/t-catchup/log?offset={offset}")
        self.assertEqual(status, 200)
        self.assertTrue(body["eof"])
        collected += body["text"]
        offset = body["next"]

        size = os.stat(os.path.join(self.logs_dir, "t-catchup.log")).st_size
        self.assertEqual(offset, size)
        self.assertEqual(body["size"], size)
        self.assertEqual(collected.encode("utf-8"), content)

    # -- 5. normal / error edges -------------------------------------------

    def test_missing_log_on_a_real_task_is_an_empty_tail(self):
        # `t-nolog` exists (setUpClass) but never gets a log file.
        self.assertFalse(os.path.exists(os.path.join(self.logs_dir, "t-nolog.log")))
        status, body = self._request("/api/tasks/t-nolog/log")
        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            {
                "task_id": "t-nolog",
                "offset": 0,
                "next": 0,
                "text": "",
                "eof": True,
                "size": 0,
                "omitted": 0,
            },
        )

    def test_unknown_task_is_404(self):
        status, body = self._request("/api/tasks/nope/log")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_bad_offsets_are_400(self):
        self._write_log("t-empty", b"hello")
        for value in ("abc", "-1"):
            status, body = self._request(f"/api/tasks/t-empty/log?offset={value}")
            self.assertEqual(status, 400, value)
            self.assertIn("error", body)

    def test_offset_past_end_is_an_empty_eof_tail(self):
        content = b"hello world"
        self._write_log("t-empty", content)
        status, body = self._request(
            f"/api/tasks/t-empty/log?offset={len(content) + 100}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["text"], "")
        self.assertTrue(body["eof"])
        self.assertEqual(body["next"], body["size"])
        self.assertEqual(body["size"], len(content))
        self.assertEqual(body["omitted"], 0)

    def test_empty_offset_is_treated_as_a_tail_request(self):
        # `?offset=` (empty value) is what the contract calls "no offset".
        self._write_log("t-empty", b"tail")
        status, body = self._request("/api/tasks/t-empty/log?offset=")
        self.assertEqual(status, 200)
        self.assertEqual(body["text"], "tail")
        self.assertTrue(body["eof"])

    # -- 6. path traversal --------------------------------------------------

    def test_path_traversal_is_404(self):
        status, body = self._request(
            "/api/tasks/..%2F..%2Fetc%2Fpasswd/log"
        )
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    # -- 7. files_changed_live: one helper, both endpoints, cached ---------

    @unittest.skipUnless(_git_available(), "git is required for the live probe")
    def test_files_changed_live_is_shared_and_cached(self):
        self.assertEqual(server.LIVE_FILES_MIN_INTERVAL, 3.0)

        detail_status, detail = self._request("/api/tasks/t-live")
        self.assertEqual(detail_status, 200)
        self.assertEqual(detail["task"]["files_changed_live"], 2)

        listed = self._task_from_list("t-live")
        self.assertEqual(listed["files_changed_live"], 2)
        # The final column is still whatever step ⑥ wrote (NULL for a running row).
        self.assertIsNone(listed["files_changed"])

        # A third change within the 3s window must be served from the cache.
        with open(os.path.join(self.git_repo, "c.txt"), "w", encoding="utf-8") as fh:
            fh.write("y\n")
        listed = self._task_from_list("t-live")
        self.assertEqual(listed["files_changed_live"], 2)  # cached, not re-probed

        # Once the task is terminal the derived field is always null.
        conn = storage.connect(storage.db_path(self.ws))
        try:
            storage.migrate(conn)
            storage.update_task(conn, "t-live", status="done")
        finally:
            conn.close()
        listed = self._task_from_list("t-live")
        self.assertIsNone(listed["files_changed_live"])

    # -- 8. quiet nulls -----------------------------------------------------

    def test_non_git_and_empty_workdir_report_null(self):
        self.assertIsNone(self._task_from_list("t-nogit")["files_changed_live"])
        self.assertIsNone(self._task_from_list("t-nowd")["files_changed_live"])
        status, body = self._request("/api/tasks/t-nogit")
        self.assertEqual(status, 200)
        self.assertIsNone(body["task"]["files_changed_live"])


class FilesChangedLiveEndToEndTest(unittest.TestCase):
    """Card 55: `files_changed_live` is fed by a REAL running task, not a fixture.

    A genuine dispatch() runs a slow `custom:` adapter on a worker thread while
    a real `server.make_server(ws, port=0)` is queried over loopback. The row is
    born running with `workdir` written before the adapter spawns (see
    dispatch._execute_claimed), so the derived count is an int during the run
    and flips back to null once the terminal write lands.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ws = os.path.join(self.tmp, "workspace")
        self.proj = os.path.join(self.tmp, "project")
        os.makedirs(self.proj)
        dispatch.prepare_workspace(self.ws)
        self._git_repo(self.proj)
        with open(
            os.path.join(self.ws, "projects.toml"), "w", encoding="utf-8"
        ) as fh:
            fh.write(
                "[defaults]\n"
                "concurrency = 1\n"
                "timeout = 60\n\n"
                "[[project]]\n"
                'id = "proj"\n'
                f'path = "{self.proj}"\n'
                'group = "proj"\n'
                'verify = "exit 0"\n'
                'verify_kind = "check"\n'
            )

        self.httpd = server.make_server(self.ws, port=0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        server._LIVE_FILES_CACHE.clear()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    @staticmethod
    def _git_repo(path):
        subprocess.run(["git", "init", "-q"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
        with open(os.path.join(path, "seed.txt"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        subprocess.run(["git", "add", "seed.txt"], cwd=path, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, check=True)

    def _request(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        request = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _row(self, task_id):
        status, body = self._request("/api/tasks")
        self.assertEqual(status, 200)
        for row in body["tasks"]:
            if row["id"] == task_id:
                return row
        self.fail(f"{task_id} not in /api/tasks")

    def _status(self, task_id):
        conn = storage.connect(storage.db_path(self.ws))
        try:
            return storage.get_task(conn, task_id)["status"]
        finally:
            conn.close()

    @unittest.skipUnless(_git_available(), "git is required for the live probe")
    def test_live_count_follows_a_real_running_task(self):
        # Seed the tree with two changes so the count has somewhere to start.
        for name in ("one.txt", "two.txt"):
            with open(os.path.join(self.proj, name), "w", encoding="utf-8") as fh:
                fh.write("x\n")

        # Dispatch on a worker so the running window can be queried before the
        # adapter exits. The id is minted inside the worker, so discover it from
        # the task list once the row lands.
        worker = threading.Thread(
            target=lambda: dispatch.dispatch(
                self.ws, "proj", "live",
                adapter="custom:sh -c 'sleep 12; echo done'",
            )
        )
        worker.start()
        try:
            deadline = time.monotonic() + 20.0
            task_id = None
            observed = None
            while time.monotonic() < deadline:
                # Wait for status + workdir: the insert and the workdir write are
                # two statements, so `running` alone can be seen a beat before the
                # path that the live probe needs.
                conn = storage.connect(storage.db_path(self.ws))
                try:
                    rows = storage.list_tasks(conn, project="proj", limit=5)
                finally:
                    conn.close()
                if rows:
                    task_id = rows[0]["id"]
                    observed = dict(rows[0])
                    if observed["status"] == STATUS_RUNNING and observed["workdir"]:
                        break
                time.sleep(0.05)
            self.assertIsNotNone(task_id, "no real task was observed")
            self.assertEqual(
                observed["status"], STATUS_RUNNING,
                "no real running task was observed",
            )

            row = self._row(task_id)
            self.assertEqual(row["status"], STATUS_RUNNING)
            # The live field is an int while the task runs (not null, not None).
            self.assertIsInstance(row["files_changed_live"], int)
            first = row["files_changed_live"]
            self.assertGreaterEqual(first, 2)

            # A new change past the 3s cache window bumps the count by one.
            with open(os.path.join(self.proj, "three.txt"), "w", encoding="utf-8") as fh:
                fh.write("y\n")
            time.sleep(server.LIVE_FILES_MIN_INTERVAL + 1.0)
            second = self._row(task_id)["files_changed_live"]
            self.assertEqual(second, first + 1)
        finally:
            worker.join(timeout=30)
        self.assertFalse(worker.is_alive())

        # The task is terminal: the live field goes null and the final column is
        # written. The adapter made no change, so it equals the seeded count.
        self.assertEqual(self._status(task_id), STATUS_DONE)
        final = self._row(task_id)
        self.assertIsNone(final["files_changed_live"])
        self.assertEqual(final["files_changed"], second)


if __name__ == "__main__":
    unittest.main()
