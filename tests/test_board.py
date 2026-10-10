"""Board renderer contract.

The board must be usable as a standalone snapshot (data inlined, no API, no
external assets) and must never render user-supplied text as live markup. The
new layout is a swimlane matrix: one row per project, six grid items each
(the sticky project lane plus five status cells), a left multi-select rail, and
one detail drawer per task.
"""

import os
import re
import tempfile
import unittest

from taskproof import dispatch, storage
from taskproof.board import render
from taskproof.models import Task

STATUS_KEYS = ("running", "verifying", "done", "failed", "timeout")


def _rowrow_block(doc, project):
    """Return the ``<div class="rowrow" data-project=...>...</div>`` slice.

    The row row uses ``display:contents`` so its children are the real grid
    items; we balance ``<div>``/``</div>`` to isolate the block.
    """
    marker = f'<div class="rowrow" data-project="{project}"'
    start = doc.index(marker)
    i, depth = start, 0
    while i < len(doc):
        if doc.startswith("</div>", i):
            depth -= 1
            i += len("</div>")
            if depth == 0:
                return doc[start:i]
        elif doc.startswith("<div", i):
            depth += 1
            i += len("<div")
        else:
            i += 1
    raise AssertionError(f"unbalanced rowrow block for {project!r}")


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

    def _insert(self, task_id, *, brief, project="proj", status="done",
                verify_cmd="exit 0", verify_exit=0):
        storage.insert_task(
            self.conn,
            Task(
                id=task_id,
                project=project,
                group=project,
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

    def _insert_event(self, task_id, event, payload=None):
        storage.append_event(self.conn, task_id, event, payload)

    # ── content ─────────────────────────────────────────────────────────

    def test_renders_id_status_and_verify_command(self):
        self._insert("t-20261007-001", brief="build the thing", status="done")
        doc = render.render_board(self.ws)
        self.assertIn("t-20261007-001", doc)
        self.assertIn("st-done", doc)
        self.assertIn("build the thing", doc)
        self.assertIn("exit 0", doc)

    def test_description_is_html_escaped(self):
        payload = "<script>alert('xss')</script>"
        self._insert("t-xss", brief=f"fix {payload}", status="done")
        doc = render.render_board(self.ws)
        # The escape hatch is: the raw payload never appears, the escaped form does.
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;", doc)
        self.assertIn("t-xss", doc)

    def test_header_tally_and_self_containment(self):
        self._insert("t-1", brief="a", status="done")
        self._insert("t-2", brief="b", status="failed", verify_exit=1)
        self._insert("t-3", brief="c", status="running")
        doc = render.render_board(self.ws)
        self.assertIn("任务<b>3</b>", doc)
        self.assertIn("处理中<b>1</b>", doc)
        self.assertIn("未通过<b>1</b>", doc)
        self.assertNotIn("worker 自称不算数", doc)
        self.assertNotIn("<link", doc)
        self.assertNotIn("http://", doc)
        self.assertNotIn("https://", doc)

    # ── matrix structure ────────────────────────────────────────────────

    def test_grid_has_project_column_and_five_status_columns(self):
        self._insert("t-1", brief="a")
        doc = render.render_board(self.ws)
        self.assertIn('<div class="hd corner">项目</div>', doc)
        for status in STATUS_KEYS:
            self.assertIn(f'class="hd st-h-{status}"', doc)
        # corner + five status headers == six header cells.
        self.assertEqual(doc.count('<div class="hd '), 6)

    def test_lane_count_matches_the_grid_template(self):
        # The CSS column count is written by hand, so it must track _STATUSES:
        # a stale repeat(N, ...) silently shifts every swimlane by a column.
        self._insert("t-1", brief="a")
        doc = render.render_board(self.ws)
        self.assertEqual(len(render._STATUSES), 5)
        self.assertIn("repeat(5,", doc)
        self.assertNotIn("repeat(6,", doc)

    def test_each_lane_wraps_six_grid_items_in_a_contents_rowrow(self):
        self._insert("t-1", brief="a", status="done")
        self._insert("t-2", brief="b", status="running")
        self._insert("t-3", brief="c", status="failed", verify_exit=1)
        doc = render.render_board(self.ws)
        self.assertIn(
            '<div class="rowrow" data-project="proj" style="display:contents">', doc
        )
        block = _rowrow_block(doc, "proj")
        self.assertEqual(block.count('<div class="lane">'), 1)
        self.assertEqual(block.count('<div class="cell">'), 5)
        self.assertEqual(
            block.count('<div class="lane">') + block.count('<div class="cell">'), 6
        )

    def test_lane_has_tally_and_status_headers_carry_counts(self):
        self._insert("t-1", brief="a", status="done")
        self._insert("t-2", brief="b", status="failed", verify_exit=1)
        doc = render.render_board(self.ws)
        block = _rowrow_block(doc, "proj")
        self.assertIn("2 任务", block)
        self.assertIn("1 未通过", block)
        # A populated status column shows its count in the header.
        self.assertIn('class="hd st-h-failed">失败<span class="n">1</span>', doc)

    # ── cards and drawers ───────────────────────────────────────────────

    def test_cards_and_drawers_are_one_to_one(self):
        self._insert("t-1", brief="a", status="done")
        self._insert("t-2", brief="b", status="failed", verify_exit=1)
        doc = render.render_board(self.ws)
        cards = re.findall(r'class="card st-[^"]+" data-task="([^"]+)"', doc)
        drawers = re.findall(r'class="drawer(?: open)?" id="([^"]+)"', doc)
        self.assertEqual(len(cards), 2)
        self.assertEqual(sorted(cards), sorted(drawers))
        self.assertEqual(set(cards), {"task-t-1", "task-t-2"})

    def test_card_button_carries_task_and_expanded_state(self):
        self._insert("t-1", brief="a", status="done")
        doc = render.render_board(self.ws)
        self.assertIn(
            '<button type="button" class="card st-done" data-task="task-t-1"'
            ' aria-expanded="false">',
            doc,
        )

    def test_rail_checkboxes_cover_every_project(self):
        self._insert("t-1", brief="a", project="alpha")
        self._insert("t-2", brief="b", project="beta")
        doc = render.render_board(self.ws)
        values = re.findall(r'<input type="checkbox" value="([^"]+)"', doc)
        projects = re.findall(r'<div class="rowrow" data-project="([^"]+)"', doc)
        self.assertEqual(set(values), set(projects))
        self.assertEqual(set(values), {"alpha", "beta"})
        self.assertIn("全选", doc)
        self.assertIn("清空", doc)

    # ── filtering ───────────────────────────────────────────────────────

    def test_project_subset_renders_only_named_lanes(self):
        self._insert("t-1", brief="a", project="alpha")
        self._insert("t-2", brief="b", project="beta")
        doc = render.render_board(self.ws, projects=["alpha"])
        self.assertIn('data-project="alpha"', doc)
        self.assertNotIn('data-project="beta"', doc)
        self.assertIn("t-1", doc)
        self.assertNotIn('data-task="task-t-2"', doc)

    def test_empty_project_list_means_all(self):
        self._insert("t-1", brief="a", project="alpha")
        self._insert("t-2", brief="b", project="beta")
        doc = render.render_board(self.ws, projects=[])
        self.assertIn('data-project="alpha"', doc)
        self.assertIn('data-project="beta"', doc)

    # ── escaping of every interpolation ─────────────────────────────────

    def test_malicious_project_brief_and_summary_are_escaped(self):
        payload = "<script>alert('xss')</script>"
        img = "<img src=x onerror=alert(1)>"
        self._insert("t-x", project="evil" + payload,
                     brief=f"fix {payload} {img} & done", status="done")
        self._insert_event("t-x", "done", {"summary": payload})
        doc = render.render_board(self.ws)
        self.assertNotIn("<script>alert", doc)
        self.assertNotIn("<img src=x", doc)
        self.assertIn("&lt;script&gt;", doc)
        self.assertIn("&amp;", doc)

    def test_task_id_is_escaped_in_card_and_drawer_ids(self):
        self._insert('t-<x>&"', brief="a", status="done")
        doc = render.render_board(self.ws)
        self.assertIn('data-task="task-t-&lt;x&gt;&amp;&quot;"', doc)
        self.assertIn('id="task-t-&lt;x&gt;&amp;&quot;"', doc)

    # ── self-contained snapshot ─────────────────────────────────────────

    def test_at_most_one_inline_script_without_external_assets(self):
        self._insert("t-1", brief="a")
        doc = render.render_board(self.ws)
        self.assertEqual(doc.count("<script"), 1)
        self.assertNotIn("<script src", doc)
        self.assertNotIn("<link", doc)
        self.assertNotIn('src="http', doc)
        self.assertNotIn('href="http', doc)

    def test_static_snapshot_has_no_absolute_urls(self):
        self._insert("t-1", brief="a")
        doc = render.render_board(self.ws, serve=False)
        self.assertNotIn("http://", doc)
        self.assertNotIn("https://", doc)


if __name__ == "__main__":
    unittest.main()
