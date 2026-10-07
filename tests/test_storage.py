"""Storage contract.

The parts that matter:
  * insert/get round-trip,
  * `update_task` refuses unknown column names (SQL-injection surface),
  * `next_task_id` is unique under concurrency — the whole reason it exists,
  * `append_event` lands in BOTH the `events` table and the JSONL stream.
"""

import json
import os
import tempfile
import threading
import unittest

from taskproof import ledger, storage
from taskproof.errors import TaskproofError
from taskproof.models import Task


def fresh_db(tmpdir):
    path = os.path.join(tmpdir, "taskproof.db")
    conn = storage.connect(path)
    storage.migrate(conn)
    return conn


def make_task(task_id="t-1", **overrides):
    kwargs = {"id": task_id, "project": "proj", "group": "grp", "brief": "do the thing"}
    kwargs.update(overrides)
    return Task(**kwargs)


class StorageCrudTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "taskproof.db")
        self.conn = fresh_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    # -- insert / get ------------------------------------------------------

    def test_insert_then_get_round_trips(self):
        storage.insert_task(self.conn, make_task("t-1"))
        row = storage.get_task(self.conn, "t-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "t-1")
        self.assertEqual(row["project"], "proj")
        self.assertEqual(row["group_name"], "grp")
        self.assertEqual(row["brief"], "do the thing")
        self.assertEqual(row["status"], "queued")
        self.assertIsNotNone(row["created_at"])

    def test_insert_defaults_status_to_queued(self):
        storage.insert_task(self.conn, {"id": "t-2", "project": "p", "brief": "b"})
        row = storage.get_task(self.conn, "t-2")
        self.assertEqual(row["status"], "queued")

    def test_get_missing_returns_none(self):
        self.assertIsNone(storage.get_task(self.conn, "nope"))

    # -- update ------------------------------------------------------------

    def test_update_task_updates_known_columns(self):
        storage.insert_task(self.conn, make_task("t-3"))
        storage.update_task(self.conn, "t-3", status="running", pid=4242)
        row = storage.get_task(self.conn, "t-3")
        self.assertEqual(row["status"], "running")
        self.assertEqual(row["pid"], 4242)

    def test_update_task_rejects_unknown_column(self):
        storage.insert_task(self.conn, make_task("t-4"))
        with self.assertRaises(TaskproofError):
            storage.update_task(self.conn, "t-4", status="running", bogus=2)
        # the rejected call must not have applied any part of the patch
        self.assertEqual(storage.get_task(self.conn, "t-4")["status"], "queued")

    def test_update_task_rejects_sql_injection_style_key(self):
        storage.insert_task(self.conn, make_task("t-5"))
        with self.assertRaises(TaskproofError):
            storage.update_task(self.conn, "t-5", **{"status=1, id='oops'": "x"})
        self.assertEqual(storage.get_task(self.conn, "t-5")["status"], "queued")

    # -- list --------------------------------------------------------------

    def test_list_tasks_filters_and_orders(self):
        storage.insert_task(self.conn, make_task("t-6", created_at="2026-10-07T09:00:00+08:00"))
        storage.insert_task(self.conn, make_task("t-7", created_at="2026-10-07T11:00:00+08:00"))
        storage.insert_task(self.conn, make_task("t-8", created_at="2026-10-07T10:00:00+08:00"))
        storage.update_task(self.conn, "t-7", status="done")

        everything = storage.list_tasks(self.conn)
        self.assertEqual([r["id"] for r in everything], ["t-7", "t-8", "t-6"])

        done = storage.list_tasks(self.conn, status="done")
        self.assertEqual([r["id"] for r in done], ["t-7"])

        many = storage.list_tasks(self.conn, status=["queued", "done"])
        self.assertEqual({r["id"] for r in many}, {"t-6", "t-7", "t-8"})

    # -- next_task_id ------------------------------------------------------

    def test_next_task_id_increments_and_formats(self):
        first = storage.next_task_id(self.conn, prefix_date="20261007")
        second = storage.next_task_id(self.conn, prefix_date="20261007")
        self.assertEqual(first, "t-20261007-001")
        self.assertEqual(second, "t-20261007-002")

    def test_next_task_id_is_per_day(self):
        storage.next_task_id(self.conn, prefix_date="20261007")
        other = storage.next_task_id(self.conn, prefix_date="20261008")
        self.assertEqual(other, "t-20261008-001")

    def test_next_task_id_respects_existing_rows(self):
        storage.insert_task(self.conn, make_task("t-20261007-004"))
        self.assertEqual(
            storage.next_task_id(self.conn, prefix_date="20261007"), "t-20261007-005"
        )

    def test_next_task_id_unique_under_concurrency(self):
        workers = 24
        ids = []
        errors = []
        barrier = threading.Barrier(workers)
        lock = threading.Lock()

        def run():
            conn = storage.connect(self.db)
            try:
                barrier.wait()
                task_id = storage.next_task_id(conn, prefix_date="20261007")
            except Exception as exc:  # pragma: no cover - surfaced in assertion
                with lock:
                    errors.append(repr(exc))
            else:
                with lock:
                    ids.append(task_id)
            finally:
                conn.close()

        threads = [threading.Thread(target=run) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(ids), workers)
        self.assertEqual(len(set(ids)), workers, f"duplicate ids: {sorted(ids)}")
        for task_id in ids:
            self.assertRegex(task_id, r"^t-20261007-\d{3}$")

    # -- events ------------------------------------------------------------

    def test_append_event_writes_table_and_jsonl(self):
        storage.insert_task(self.conn, make_task("t-9"))
        storage.append_event(self.conn, "t-9", "started", {"step": 1})

        rows = storage.list_events(self.conn, "t-9")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], "started")
        self.assertEqual(json.loads(rows[0]["payload"]), {"step": 1})

        stream = ledger.stream_path(self.tmp.name)
        self.assertTrue(os.path.exists(stream), stream)
        with open(stream, encoding="utf-8") as fh:
            lines = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["event"], "started")
        self.assertEqual(lines[0]["task_id"], "t-9")
        self.assertEqual(lines[0]["payload"], {"step": 1})
        # both sinks carry the same timestamp / content
        self.assertEqual(lines[0]["ts"], rows[0]["ts"])
        self.assertEqual(lines[0]["event"], rows[0]["event"])

    def test_append_event_without_payload(self):
        storage.insert_task(self.conn, make_task("t-10"))
        storage.append_event(self.conn, "t-10", "queued")
        rows = storage.list_events(self.conn, "t-10")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["payload"])

    def test_list_events_is_scoped_and_ordered(self):
        storage.append_event(self.conn, "t-1", "a")
        storage.append_event(self.conn, "t-2", "b")
        storage.append_event(self.conn, "t-1", "c")
        events = storage.list_events(self.conn, "t-1")
        self.assertEqual([e["event"] for e in events], ["a", "c"])


if __name__ == "__main__":
    unittest.main()
