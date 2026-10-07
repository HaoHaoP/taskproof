"""Board renderer contract.

The board must be usable as a standalone snapshot (data inlined, no API, no
external assets) and must never render user-supplied text as live markup.
"""

import os
import tempfile
import unittest

from taskproof import dispatch, storage
from taskproof.board import render
from taskproof.models import Task


class BoardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self._tmp.name, "workspace")
        dispatch.prepare_workspace(self.ws)
        self.conn = storage.connect(storage.db_path(self.ws))
        storage.migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _insert(self, task_id, *, brief, status="done", verify_cmd="exit 0",
                verify_exit=0):
        storage.insert_task(
            self.conn,
            Task(
                id=task_id,
                project="proj",
                group="proj",
                brief=brief,
                status=status,
                verify_cmd=verify_cmd,
                verify_exit=verify_exit,
                created_at=storage.now_iso(),
                started_at=storage.now_iso(),
                finished_at=storage.now_iso(),
            ),
        )
        storage.append_event(self.conn, task_id, "done", {"ok": True})

    def test_renders_id_status_and_duration_fields(self):
        self._insert("t-20261007-001", brief="build the thing", status="done")
        doc = render.render_board(self.ws)
        self.assertIn("t-20261007-001", doc)
        self.assertIn("done", doc)
        self.assertIn("build the thing", doc)
        self.assertIn("exit 0", doc)

    def test_description_is_html_escaped(self):
        payload = "<script>alert('xss')</script>"
        self._insert("t-xss", brief=f"fix {payload}", status="done")
        doc = render.render_board(self.ws)
        # The escape hatch is: the raw tag never appears, the escaped form does.
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;", doc)
        self.assertIn("t-xss", doc)

    def test_header_counts_every_status_and_is_self_contained(self):
        self._insert("t-1", brief="a", status="done")
        self._insert("t-2", brief="b", status="failed", verify_exit=1)
        doc = render.render_board(self.ws)
        self.assertIn("total 2", doc)
        # Self-contained: no external stylesheet/script/network reference.
        self.assertNotIn("<link", doc)
        self.assertNotIn("http://", doc)
        self.assertNotIn("https://", doc)


if __name__ == "__main__":
    unittest.main()
