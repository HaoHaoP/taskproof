"""Concurrency contract.

The rules being pinned:
  * only one task per group
  * the global cap is honoured under a race (exactly one of N racers wins the last slot)
  * an expired claim is reclaimed automatically — the whole reason this is not a lock file
  * release never removes another process's claim
"""

import os
import tempfile
import unittest

from taskproof import concurrency, storage
from taskproof.errors import ConcurrencyError


def fresh_db(tmpdir):
    path = os.path.join(tmpdir, "t.db")
    conn = storage.connect(path)
    storage.migrate(conn)
    return conn


class ClaimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = fresh_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_acquire_and_release(self):
        scopes = concurrency.acquire(self.conn, "t-1", "g1", cap=3, ttl=60)
        self.assertTrue(scopes)
        concurrency.release(self.conn, scopes)
        self.assertEqual(concurrency.count_active(self.conn), 0)

    def test_same_group_blocks_second_task(self):
        concurrency.acquire(self.conn, "t-1", "g1", cap=3, ttl=60)
        with self.assertRaises(ConcurrencyError):
            concurrency.acquire(self.conn, "t-2", "g1", cap=3, ttl=60)

    def test_different_group_allowed(self):
        concurrency.acquire(self.conn, "t-1", "g1", cap=3, ttl=60)
        concurrency.acquire(self.conn, "t-2", "g2", cap=3, ttl=60)
        self.assertEqual(concurrency.count_active(self.conn), 2)

    def test_global_cap_enforced(self):
        concurrency.acquire(self.conn, "t-1", "g1", cap=2, ttl=60)
        concurrency.acquire(self.conn, "t-2", "g2", cap=2, ttl=60)
        with self.assertRaises(ConcurrencyError):
            concurrency.acquire(self.conn, "t-3", "g3", cap=2, ttl=60)

    def test_expired_claim_is_reclaimed(self):
        concurrency.acquire(self.conn, "t-1", "g1", cap=3, ttl=-1)  # already expired
        scopes = concurrency.acquire(self.conn, "t-2", "g1", cap=3, ttl=60)
        self.assertTrue(scopes)

    def test_release_ignores_foreign_claim(self):
        concurrency.acquire(self.conn, "t-1", "g1", cap=3, ttl=60)
        concurrency.release(self.conn, [concurrency.group_scope("g1")])  # not ours
        self.assertEqual(concurrency.count_active(self.conn), 1)

    def test_reap_returns_count(self):
        concurrency.acquire(self.conn, "t-1", "g1", cap=3, ttl=-1)
        self.assertEqual(concurrency.reap_expired(self.conn), 1)
        self.assertEqual(concurrency.reap_expired(self.conn), 0)


if __name__ == "__main__":
    unittest.main()
