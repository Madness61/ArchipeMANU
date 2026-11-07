"""Filesystem integration checks without executing Archipelago or using real data."""
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from hub import ap_bridge, config, db, stats


class BridgeTests(unittest.TestCase):
    def test_automatic_loader_retries_changes_while_running(self):
        entered = threading.Event()
        release = threading.Event()
        attempts = []

        def fake_extract():
            attempts.append(True)
            if len(attempts) == 1:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test timed out")
                raise ValueError("fake import failure")
            return True

        with patch.object(ap_bridge, "extract", side_effect=fake_extract), \
                patch.object(ap_bridge, "_write_status") as status:
            ap_bridge.start_extract()
            worker = ap_bridge._extract_thread
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(status.call_args_list[0].kwargs["status"], "queued")
                ap_bridge.start_extract()
                self.assertIs(ap_bridge._extract_thread, worker)
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(attempts), 2)
            self.assertIsNone(ap_bridge._extract_thread)
            self.assertTrue(any(call.kwargs.get("status") == "error" for call in status.call_args_list))

    def test_custom_execution_default_and_explicit_disable(self):
        with patch.dict(os.environ):
            os.environ.pop("HUB_TRUSTED_APWORLDS", None)
            self.assertTrue(ap_bridge.trusted_custom_execution())
            os.environ["HUB_TRUSTED_APWORLDS"] = "0"
            self.assertFalse(ap_bridge.trusted_custom_execution())

    def test_sync_checks_bytes_and_retires_only_managed_worlds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            worlds = root / "uploads"
            source = root / "AP"
            worlds.mkdir()
            source.mkdir()
            with patch.object(config, "APWORLDS", worlds), patch.object(config, "AP_SOURCE", source), \
                    patch.dict(os.environ, {"HUB_TRUSTED_APWORLDS": "1"}):
                active = worlds / "test.apworld"
                active.write_bytes(b"old")
                ap_bridge._sync_custom_worlds()
                target = source / "custom_worlds" / active.name
                manual = target.with_name("manual.apworld")
                manual.write_bytes(b"manual")
                active.write_bytes(b"new")
                os.utime(active, (1, 1))
                ap_bridge._sync_custom_worlds()
                self.assertEqual(target.read_bytes(), b"new")
                active.unlink()
                ap_bridge._sync_custom_worlds()
                self.assertFalse(target.exists())
                self.assertEqual(manual.read_bytes(), b"manual")
                retired = target.parent / ".hub-inactive" / hashlib.sha256(b"new").hexdigest()
                self.assertEqual(retired.read_bytes(), b"new")

    def test_sync_refuses_to_retire_manually_modified_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            worlds = root / "uploads"
            source = root / "AP"
            worlds.mkdir()
            source.mkdir()
            with patch.object(config, "APWORLDS", worlds), patch.object(config, "AP_SOURCE", source), \
                    patch.dict(os.environ, {"HUB_TRUSTED_APWORLDS": "1"}):
                active = worlds / "test.apworld"
                active.write_bytes(b"old")
                ap_bridge._sync_custom_worlds()
                target = source / "custom_worlds" / active.name
                target.write_bytes(b"manual changes")
                active.unlink()
                with self.assertRaises(ValueError):
                    ap_bridge._sync_custom_worlds()
                self.assertEqual(target.read_bytes(), b"manual changes")


class TransactionTests(unittest.TestCase):
    def test_commit_rollback_and_connection_closure_preserve_existing_rows(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(config, "DB_PATH", Path(folder) / "hub.db"):
            with db.transaction() as conn:
                conn.execute("CREATE TABLE records(value TEXT)")
                conn.execute("INSERT INTO records VALUES ('existing')")
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")
            with self.assertRaises(RuntimeError):
                with db.transaction() as failed:
                    failed.execute("INSERT INTO records VALUES ('rolled back')")
                    raise RuntimeError("abort")
            with self.assertRaises(sqlite3.ProgrammingError):
                failed.execute("SELECT 1")
            with db.transaction() as check:
                self.assertEqual([r[0] for r in check.execute("SELECT value FROM records")], ["existing"])


class DistributionTests(unittest.TestCase):
    def test_consistency_and_exclusion_of_group_slots(self):
        data = stats.aggregate_placements(
            [{"id": 1, "name": "A", "game": "A"}, {"id": 2, "name": "B", "game": "B"}],
            [(1, 2, "progression"), (2, 1, "trap"), (1, 3, "useful"), (3, 1, "filler")])
        self.assertTrue(stats.valid_distribution(data))
        self.assertEqual(data["total_placements"], 2)
        data["matrix"]["1"]["2"] += 1
        self.assertFalse(stats.valid_distribution(data))
