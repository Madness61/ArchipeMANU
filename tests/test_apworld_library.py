"""Versioned APWorld storage: persistence, migration and safety checks."""
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from hub import apworld_library as library
from hub import config


def make_world(code=b"v1", module="test_world"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_out:
        zip_out.writestr(f"{module}/__init__.py", code)
        zip_out.writestr(f"{module}/archipelago.json",
                         '{"game":"Test World","world_version":"1.0"}')
    return buffer.getvalue()


class APWorldLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_data = config.DATA
        self.original_apworlds = config.APWORLDS
        config.DATA = Path(self.temp.name)
        config.APWORLDS = config.DATA / "apworlds"

    def tearDown(self):
        config.DATA = self.original_data
        config.APWORLDS = self.original_apworlds
        self.temp.cleanup()

    def test_upload_preserves_versions_and_can_reactivate(self):
        first = make_world(b"old")
        second = make_world(b"new")
        v1 = library.store(first)
        v2 = library.store(second)
        self.assertNotEqual(v1["sha256"], v2["sha256"])
        self.assertEqual(2, len(library.list_versions()))
        self.assertEqual([v2["sha256"]], [v["sha256"] for v in library.list_versions() if v["active"]])
        library.activate(v1["sha256"])
        self.assertEqual(first, (config.APWORLDS / "test_world.apworld").read_bytes())
        self.assertEqual(second, library.archived_file(v2["sha256"]).read_bytes())
        self.assertEqual(2, len(library.list_versions()))  # Fresh DB connection

    def test_existing_flat_upload_migrates_without_removal(self):
        config.APWORLDS.mkdir(parents=True)
        previous = make_world()
        (config.APWORLDS / "test_world.apworld").write_bytes(previous)
        versions = library.list_versions()
        self.assertEqual(1, len(versions))
        self.assertTrue(versions[0]["active"])
        self.assertEqual(previous, library.archived_file(versions[0]["sha256"]).read_bytes())
        self.assertEqual(previous, (config.APWORLDS / "test_world.apworld").read_bytes())

    def test_existing_old_versions_are_imported(self):
        older = make_world(b"older")
        current = make_world(b"current")
        old_folder = config.APWORLDS / "_old"
        old_folder.mkdir(parents=True)
        (old_folder / "legacy.apworld").write_bytes(older)
        (config.APWORLDS / "test_world.apworld").write_bytes(current)
        versions = library.list_versions()
        self.assertEqual(2, len(versions))
        self.assertEqual(1, sum(v["active"] for v in versions))
        self.assertEqual(current, library.archived_file(next(v["sha256"] for v in versions if v["active"])).read_bytes())
        self.assertTrue((old_folder / "legacy.apworld").exists())

    def test_deactivate_keeps_downloads(self):
        added = library.store(make_world())
        library.deactivate("test_world")
        self.assertFalse((config.APWORLDS / "test_world.apworld").exists())
        self.assertFalse(any(v["active"] for v in library.list_versions()))
        self.assertTrue(library.archived_file(added["sha256"]).exists())

    def test_archive_traversal_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as out:
            out.writestr("test_world/__init__.py", "")
            out.writestr("../escape.py", "unsafe")
        with self.assertRaisesRegex(ValueError, "Unsicherer Pfad"):
            library.inspect_bytes(buffer.getvalue())

    def test_invalid_module_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Modulname"):
            library.inspect_bytes(make_world(module="InvalidModule"))

    def test_corrupt_archived_file_cannot_be_activated(self):
        v = library.store(make_world())
        archived = library.archived_file(v["sha256"])
        archived.write_bytes(b"bad")
        with self.assertRaises(ValueError):
            library.activate(v["sha256"])


if __name__ == "__main__":
    unittest.main()
