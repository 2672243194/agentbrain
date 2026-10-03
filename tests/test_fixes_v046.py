"""Regression tests for the python -m entry point, MCP launch hint,
and lint remedy hints."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

from agentbrain.api import memory_lint
from agentbrain.doctor import doctor
from agentbrain.vault import Vault


def test_python_m_entry_point_invokes_cli():
    r = subprocess.run(
        [sys.executable, "-m", "agentbrain", "--version"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert r.stdout.startswith("agentbrain ")


def test_doctor_mcp_hint_uses_installed_python(vault: Vault):
    out = doctor(vault)
    config = json.loads(out.split("```json\n", 1)[1].split("\n```", 1)[0])
    server = config["mcpServers"]["agentbrain"]
    assert server["command"] == sys.executable
    assert server["args"] == (["-I"] if sys.flags.isolated else []) + ["-m", "agentbrain", "serve"]


def test_lint_findings_carry_remedy_hints(vault: Vault):
    old = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    expired = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    a = vault.learnings_dir / "remedy-case-lesson-01.md"
    a.write_text(
        "---\ncase_id: remedy-case\ntags: []\nsource_summary: remedy lesson a\n"
        f"last_verified_at: {old}\nvalid_until: {expired}\nconfidence: 0.3\n"
        "use_count: 0\n---\n\nbody\n",
        encoding="utf-8",
    )
    b = vault.learnings_dir / "remedy-case-lesson-02.md"
    b.write_text(
        "---\ncase_id: remedy-case\ntags: [t]\nsource_summary: remedy lesson b\n"
        "superseded_by: ghost-lesson-99\nuse_count: 0\n---\n\nbody\n",
        encoding="utf-8",
    )
    c = vault.learnings_dir / "remedy-case-lesson-03.md"
    c.write_text(
        "---\ncase_id: remedy-case\ntags: [t]\nsource_summary: twin summary\n"
        "use_count: 0\n---\n\nbody\n",
        encoding="utf-8",
    )
    d = vault.learnings_dir / "remedy-case-lesson-04.md"
    d.write_text(
        "---\ncase_id: remedy-case\ntags: [t]\nsource_summary: twin summary\n"
        "use_count: 0\n---\n\nbody\n",
        encoding="utf-8",
    )
    out = memory_lint(vault=vault)
    assert "remedy: agentbrain verify remedy-case-lesson-01" in out
    assert "remedy: update valid_until by hand or supersede the lesson" in out
    assert "remedy: add tags in the lesson file" in out
    assert "remedy: adjust confidence by hand" in out
    assert "remedy: fix superseded_by by hand" in out
    assert "merge proposal below" in out
