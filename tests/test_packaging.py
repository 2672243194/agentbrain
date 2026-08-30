"""Packaging invariants: single-sourced version and CI workflow shape."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

import agentbrain

_ROOT = Path(__file__).resolve().parents[1]


def test_version_is_single_sourced():
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in text
    assert 'version = {attr = "agentbrain.__version__"}' in text
    assert not re.search(r'(?m)^version = "\d', text)  # no static copy to drift


def test_dynamic_version_resolves_to_package_version():
    from setuptools.config.pyprojecttoml import read_configuration

    cfg = read_configuration(str(_ROOT / "pyproject.toml"), ignore_option_errors=False)
    assert cfg["project"]["version"] == agentbrain.__version__


def test_version_follows_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", agentbrain.__version__)


def test_ci_workflow_is_valid_yaml():
    data = yaml.safe_load(
        (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    job = data["jobs"]["test"]
    assert set(job["strategy"]["matrix"]["os"]) == {"ubuntu-latest", "windows-latest"}
    assert job["strategy"]["matrix"]["python-version"] == ["3.10", "3.11", "3.12"]
    assert job["steps"][-1]["run"].startswith("python -m pytest")
