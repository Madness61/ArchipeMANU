"""Browser-server isolation guards can be tested without installing Playwright."""
from pathlib import Path
import tempfile
import unittest

from browser_tests.fixtures import ROOT_MARKER
from browser_tests.server import checked_root
from browser_tests.safety import checked_artifact_path


class BrowserIsolationTests(unittest.TestCase):
    def test_artifact_overrides_cannot_point_at_production_data(self):
        workspace = Path(__file__).resolve().parent.parent
        for path in (workspace/"data",workspace,Path(tempfile.gettempdir())):
            with self.assertRaises(ValueError):
                checked_artifact_path(path)
        self.assertEqual(checked_artifact_path(workspace/"test-results"/"browser"),
                         (workspace/"test-results"/"browser").resolve())

    def test_workspace_and_production_data_can_never_be_test_roots(self):
        workspace = Path(__file__).resolve().parent.parent
        for path in (workspace,workspace/"data",Path("data")):
            with self.assertRaises(ValueError):
                checked_root(path)

    def test_temporary_root_needs_expected_prefix_and_explicit_marker(self):
        with tempfile.TemporaryDirectory(prefix="archipemanu-browser-") as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                checked_root(root)
            (root/".browser-test-root").write_text("wrong marker",encoding="utf-8")
            with self.assertRaises(ValueError):
                checked_root(root)
            (root/".browser-test-root").write_text(ROOT_MARKER,encoding="utf-8")
            self.assertEqual(checked_root(root),root.resolve())

    def test_unrelated_temp_directories_are_rejected_even_with_marker(self):
        with tempfile.TemporaryDirectory(prefix="unrelated-") as folder:
            root = Path(folder)
            (root/".browser-test-root").write_text(ROOT_MARKER,encoding="utf-8")
            with self.assertRaises(ValueError):
                checked_root(root)
