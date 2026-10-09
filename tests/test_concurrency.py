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


class AutoDetectTest(unittest.TestCase):
    """Card 42: the auto-detected fallback cap — pure, conservative, stable."""

    def test_one_slot_per_four_cores(self):
        self.assertEqual(concurrency._auto_cap(14, 48 * 1024 ** 3)[0], 3)
        self.assertEqual(concurrency._auto_cap(20, 48 * 1024 ** 3)[0], 5)

    def test_floor_is_two(self):
        self.assertEqual(concurrency._auto_cap(4, 32 * 1024 ** 3)[0], 2)
        self.assertEqual(concurrency._auto_cap(2, 32 * 1024 ** 3)[0], 2)

    def test_ceiling_is_six(self):
        value, detail = concurrency._auto_cap(40, 256 * 1024 ** 3)
        self.assertEqual(value, 6)
        self.assertIn("40 核", detail)

    def test_small_memory_is_two_regardless_of_cores(self):
        value, detail = concurrency._auto_cap(64, 4 * 1024 ** 3)
        self.assertEqual(value, 2)
        self.assertIn("内存", detail)

    def test_unknown_cores_falls_back_to_three(self):
        self.assertEqual(concurrency._auto_cap(None, 48 * 1024 ** 3)[0], 3)
        self.assertEqual(concurrency._auto_cap(0, None)[0], 3)
        self.assertEqual(concurrency._auto_cap(-1, None)[0], 3)

    def test_detect_is_stable_and_bounded(self):
        first = concurrency.detect()
        self.assertEqual(first, concurrency.detect())
        self.assertGreaterEqual(first, 2)
        self.assertLessEqual(first, 6)
        self.assertIsInstance(concurrency.detect_detail(), str)

    def test_memory_probe_never_raises(self):
        value = concurrency._physical_memory_bytes()
        self.assertTrue(value is None or value > 0)


class ResolveTest(unittest.TestCase):
    """Card 42: the three-state source resolution — cli > toml > auto."""

    def test_cli_cap_wins_over_toml(self):
        setting = concurrency.resolve({"concurrency": 5}, 1)
        self.assertEqual((setting.value, setting.source), (1, "cli"))
        self.assertIn("--cap 1", setting.detail)

    def test_toml_beats_auto(self):
        setting = concurrency.resolve({"concurrency": 5})
        self.assertEqual((setting.value, setting.source), (5, "toml"))
        self.assertEqual(setting.detail, "projects.toml")

    def test_auto_when_unset(self):
        for defaults in (None, {}):
            setting = concurrency.resolve(defaults)
            self.assertEqual(setting.source, "auto")
            self.assertEqual(setting.value, concurrency.detect())

    def test_wire_shape(self):
        setting = concurrency.resolve({"concurrency": 4})
        self.assertEqual(
            setting.as_dict(),
            {"value": 4, "source": "toml", "detail": "projects.toml"},
        )

    def test_source_labels_are_three_distinct_states(self):
        auto = concurrency.CapSetting(3, concurrency.SOURCE_AUTO, "14 核 ÷ 4")
        toml = concurrency.CapSetting(5, concurrency.SOURCE_TOML, "projects.toml")
        cli = concurrency.CapSetting(7, concurrency.SOURCE_CLI, "--cap 7")
        self.assertEqual(concurrency.source_label(auto), "自动探测 14 核 ÷ 4")
        self.assertEqual(concurrency.source_label(toml), "projects.toml")
        self.assertEqual(concurrency.source_label(cli), "本次 --cap 7")
        self.assertEqual(concurrency.source_gloss(auto), "自动探测：14 核 ÷ 4")


if __name__ == "__main__":
    unittest.main()
