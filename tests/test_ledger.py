"""Audit-stream rotation contract.

The rule that matters: rotation must NEVER destroy the current month, and must
not touch files it did not create.
"""

import json
import os
import tempfile
import unittest

from taskproof import ledger


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_writes_one_line(self):
        path = ledger.append(self.dir, {"event": "started", "task_id": "t-1", "ts": "2026-10-07T10:00:00+08:00"})
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            lines = [l for l in fh if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event"], "started")

    def test_append_routes_by_month(self):
        p1 = ledger.append(self.dir, {"event": "a", "ts": "2026-09-30T23:59:59+08:00"})
        p2 = ledger.append(self.dir, {"event": "b", "ts": "2026-10-01T00:00:01+08:00"})
        self.assertNotEqual(p1, p2)
        self.assertIn("2026-09", p1)
        self.assertIn("2026-10", p2)

    def test_rotate_compresses_old_months_and_keeps_current(self):
        ledger.append(self.dir, {"event": "old", "ts": "2026-01-15T10:00:00+08:00"})
        ledger.append(self.dir, {"event": "new", "ts": "2026-10-15T10:00:00+08:00"})
        ledger.rotate(self.dir, keep_months=3)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "events-2026-01.jsonl.gz")))
        self.assertTrue(os.path.exists(ledger.stream_path(self.dir, "2026-10")))

    def test_rotate_prunes_beyond_keep_window(self):
        ledger.append(self.dir, {"event": "ancient", "ts": "2020-01-01T10:00:00+08:00"})
        ledger.rotate(self.dir, keep_months=2)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "events-2020-01.jsonl.gz")))

    def test_iter_events_reads_plain_and_gz(self):
        ledger.append(self.dir, {"event": "old", "ts": "2026-01-15T10:00:00+08:00"})
        ledger.append(self.dir, {"event": "new", "ts": "2026-10-15T10:00:00+08:00"})
        ledger.rotate(self.dir, keep_months=12)
        events = list(ledger.iter_events(self.dir))
        self.assertEqual({e["event"] for e in events}, {"old", "new"})

    def test_iter_events_filters_by_task(self):
        ledger.append(self.dir, {"event": "a", "task_id": "t-1", "ts": "2026-10-01T10:00:00+08:00"})
        ledger.append(self.dir, {"event": "b", "task_id": "t-2", "ts": "2026-10-01T11:00:00+08:00"})
        self.assertEqual([e["event"] for e in ledger.iter_events(self.dir, task_id="t-2")], ["b"])

    def test_torn_line_does_not_break_read(self):
        path = ledger.append(self.dir, {"event": "ok", "ts": "2026-10-01T10:00:00+08:00"})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"event": "torn"')  # no newline, no closing brace
        self.assertEqual(len(list(ledger.iter_events(self.dir))), 1)


if __name__ == "__main__":
    unittest.main()
