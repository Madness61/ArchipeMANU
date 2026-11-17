"""Refactoring must preserve public routes, entry points and documentation paths."""
import ast
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts.check_docs import broken_links, documents
import test_mvp as fixtures

ROOT = Path(__file__).resolve().parents[1]


class RouteContractTests(unittest.TestCase):
    setUp, tearDown = fixtures.MVPTests.setUp, fixtures.MVPTests.tearDown

    def test_all_existing_endpoint_names_paths_and_methods_are_preserved(self):
        original = json.loads((ROOT/'tests/fixtures/route_contract.json').read_text(encoding='utf-8'))
        actual = {(r.rule, r.endpoint, tuple(sorted(r.methods-{'HEAD', 'OPTIONS'})))
                  for r in self.app.url_map.iter_rules() if r.endpoint != 'static'}
        expected = {(r['rule'], r['endpoint'], tuple(r['methods'])) for r in original}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(original))

    def test_compatibility_imports_use_exactly_the_canonical_module(self):
        for old, new in (('ap_bridge', 'integrations.archipelago'), ('ap_console', 'integrations.console'),
                         ('mvp', 'services.rounds'), ('progression', 'services.progression')):
            with self.subTest(old=old):
                self.assertIs(importlib.import_module('hub.'+old), importlib.import_module('hub.'+new))


class RepositoryContractTests(unittest.TestCase):
    def test_internal_markdown_links_and_heading_anchors(self):
        self.assertEqual(list(broken_links()), [])
        self.assertEqual({p.name for p in ROOT.glob('*.md')}, {'README.md'})
        self.assertGreater(len(list(documents())), 20)

    def test_markdown_checker_reports_missing_file_and_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            # Also exercises Windows short temp paths: the supplied root need
            # not equal its canonical resolved spelling. Valid anchors stay valid.
            root = Path(directory)/'..'/Path(directory).name
            (root/'README.md').write_text('# One\n[Missing](missing.md)\n[Heading](#wrong)\n[Good](#one)', encoding='utf-8')
            errors = list(broken_links(root))
            self.assertEqual(len(errors), 2)
            self.assertTrue(any('missing path' in e for e in errors))
            self.assertTrue(any('missing heading' in e for e in errors))

    def test_all_application_modules_and_worker_entrypoints_import_without_ap_or_data(self):
        # Fresh interpreter exercises import order and asserts that importing the
        # application never creates a DB, starts a worker or imports AP rules.
        code = '''import importlib, pkgutil, sys
import hub
for info in pkgutil.walk_packages(hub.__path__, 'hub.'):
    importlib.import_module(info.name)
for module in ('ap_runner','progression_worker','progression_model','progression.engine','progression.goals','logic_worker'):
    importlib.import_module(module)
assert 'BaseClasses' not in sys.modules
from hub import config
assert not config.DATA.exists()
'''
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, HUB_DATA=str(Path(directory)/'unused-data'), PYTHONIOENCODING='utf-8')
            result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_cli_help_keeps_data_and_external_installation_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)/'unused-data'
            env = dict(os.environ, HUB_DATA=str(data), PYTHONIOENCODING='utf-8')
            for command in (['-m', 'hub', '--help'], ['ap_runner.py', '--help']):
                result = subprocess.run([sys.executable, *command], cwd=ROOT, env=env, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
                self.assertFalse(data.exists())

    @unittest.skipUnless(os.name == 'nt', 'PowerShell parser checked on Windows')
    def test_powershell_scripts_parse_without_execution(self):
        shell = shutil.which('powershell') or shutil.which('pwsh')
        self.assertIsNotNone(shell)
        for name in ('setup.ps1', 'start.ps1', 'test-browser.ps1'):
            # Parser only: never run setup/start against an actual AP checkout.
            script = "$tokens=$null; $problems=$null; [System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$problems) | Out-Null; if ($problems.Count) { $problems | ForEach-Object { $_.Message }; exit 1 }"
            result = subprocess.run([shell, '-NoProfile', '-Command', '& { '+script+' }', str(ROOT/name)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, (name, result.stdout, result.stderr))

    def test_supported_entrypoints_preserve_commands_and_python_syntax(self):
        # The supported wrappers are PowerShell scripts. Their syntax is parsed
        # above on Windows; there are no Unix .sh wrappers in this repository.
        for filename, command in (('setup.ps1', 'ModuleUpdate.py --yes --append'),
                                  ('start.ps1', '-m hub'),
                                  ('test-browser.ps1', '@("-m", "browser_tests")')):
            source = (ROOT/filename).read_text(encoding='utf-8')
            self.assertIn(command, source, filename)
            self.assertIn('$PSScriptRoot', source, filename)
        for filename in ('ap_runner.py', 'progression_worker.py', 'logic_worker.py', 'hub/__main__.py'):
            source = (ROOT/filename).read_text(encoding='utf-8')
            ast.parse(source, filename)
            self.assertIn('if __name__', source, filename)

    def test_browser_wrapper_links_to_the_current_setup_instructions(self):
        source = (ROOT/'test-browser.ps1').read_text(encoding='utf-8')
        self.assertIn('docs/DEVELOPMENT.md', source)
        self.assertTrue((ROOT/'docs/DEVELOPMENT.md').is_file())

    def test_production_worker_never_imports_the_combination_extension(self):
        for path in [ROOT/'progression_worker.py', ROOT/'progression_model.py',
                     *list((ROOT/'hub').rglob('*.py')), *list((ROOT/'progression').glob('*.py'))]:
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn('progression.extensions', node.module or '', str(path))
                    self.assertNotEqual(node.module, 'progression_recommendations', str(path))

    def test_integrations_do_not_import_http_routes_or_factory(self):
        for path in (ROOT/'hub/integrations').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith(('hub.routes', 'hub.app')), str(path))
