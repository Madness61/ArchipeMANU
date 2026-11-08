"""Run with: python -m browser_tests [pytest options]."""
import os
import importlib.util
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent.parent
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH",str(root/".playwright-browsers"))
    try:
        import pytest
        if importlib.util.find_spec("pytest_playwright") is None:
            raise ImportError("pytest-playwright")
    except ImportError:
        raise SystemExit("Zuerst: python -m pip install -r requirements-browser.txt")
    raise SystemExit(pytest.main([str(root/"browser_tests"),"-v","--junitxml="+str(root/"test-results"/"browser-junit.xml"),*sys.argv[1:]]))


if __name__ == "__main__":
    main()
