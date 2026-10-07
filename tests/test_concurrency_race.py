"""Atomicity coverage for `acquire` (the sequential contract lives in
tests/test_concurrency.py).

A single `BEGIN IMMEDIATE` transaction must make "reap -> check -> count ->
insert" indivisible, so several processes racing for the *last* global slot
produce exactly one winner — never zero, never two.
"""

import multiprocessing as mp
import os
import tempfile
import unittest

from taskproof import concurrency, storage
from taskproof.errors import ConcurrencyError

TTL = 60


def _racer(db_path, cap, start, done, results):
    """Runs in a child process: grab the slot, report, hold, then release."""
    conn = storage.connect(db_path)
    won = False
    scopes = []
    try:
        start.wait()
        try:
            scopes = concurrency.acquire(
                conn, f"t-{os.getpid()}", f"g-{os.getpid()}", cap=cap, ttl=TTL
            )
            won = True
        except ConcurrencyError:
            won = False
        results.put(won)
        # Keep the claim until every racer has attempted, so no racer can slip
        # into a slot the winner has already silently freed.
        done.wait(timeout=30)
    except BaseException:
        results.put(won)
    finally:
        if won:
            try:
                concurrency.release(conn, scopes)
            except Exception:
                pass
        conn.close()


class RaceTest(unittest.TestCase):
    def _race(self, n, cap):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = os.path.join(tmp.name, "t.db")
        conn = storage.connect(db)
        storage.migrate(conn)
        conn.close()

        try:
            ctx = mp.get_context("fork")
        except ValueError:
            ctx = mp.get_context()
        start = ctx.Barrier(n)
        done = ctx.Barrier(n)
        results = ctx.Queue()
        procs = [
            ctx.Process(target=_racer, args=(db, cap, start, done, results))
            for _ in range(n)
        ]
        for p in procs:
            p.start()
        outcomes = []
        for _ in range(n):
            try:
                outcomes.append(results.get(timeout=60))
            except Exception:
                outcomes.append(None)
        for p in procs:
            p.join(timeout=60)
            self.assertFalse(p.is_alive(), "racer did not exit")

        conn = storage.connect(db)
        try:
            self.assertEqual(concurrency.count_active(conn), 0, "a slot leaked")
        finally:
            conn.close()
        return outcomes

    def test_exactly_one_winner_for_last_global_slot(self):
        outcomes = self._race(n=6, cap=1)
        self.assertEqual(outcomes.count(True), 1, f"outcomes={outcomes}")

    def test_cap_two_lets_exactly_two_win(self):
        outcomes = self._race(n=6, cap=2)
        self.assertEqual(outcomes.count(True), 2, f"outcomes={outcomes}")


if __name__ == "__main__":
    unittest.main()
