"""Regression tests for the v0.4.6 batch: python -m entry point, MCP hint
fallback, and lint remedy hints."""
from __future__ import annotations

import datetime as dt
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


def test_doctor_mcp_hint_offers_python_m_fallback(vault: Vault):
    out = doctor(vault)
    assert '"args": ["-m", "agentbrain", "serve"]' in out


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
