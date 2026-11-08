"""Protect production data from test-runner options that recursively clear output."""
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def checked_artifact_path(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(PROJECT/"test-results"):
        raise ValueError("Browser-Testartefakte sind ausschließlich unter test-results/ erlaubt.")
    return resolved
