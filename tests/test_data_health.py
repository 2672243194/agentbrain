"""Data-health visibility and input hardening tests (v0.4.6 batch)."""
from __future__ import annotations

from agentbrain import cli
from agentbrain.api import memory_ingest
from agentbrain.doctor import doctor
from agentbrain.vault import Vault


def test_doctor_reports_broken_lesson_file(vault: Vault):
    (vault.learnings_dir / "mangled-lesson-01.md").write_text(
        "---\ncase_id: [unclosed\ntags: broken\n  bad indent: :\n---\n\nbody\n",
        encoding="utf-8",
    )
    out = doctor(vault)
    assert "broken lesson file(s)" in out
    assert "mangled-lesson-01.md" in out
    assert "1 issue(s) found" in out


def test_doctor_ignores_stray_notes_without_frontmatter(vault: Vault):
    (vault.learnings_dir / "README.md").write_text(
        "# notes\n\nA human note, not a lesson.\n", encoding="utf-8"
    )
    out = doctor(vault)
    assert "broken" not in out
    assert "Everything looks healthy." in out


def test_doctor_exit_1_on_broken_files(vault: Vault):
    (vault.learnings_dir / "mangled-lesson-01.md").write_text(
        "---\ncase_id: [unclosed\n---\n\nbody\n", encoding="utf-8"
    )
    assert cli.main(["--vault", str(vault.root), "doctor"]) == 1


def test_get_rejects_path_separators_in_id(vault: Vault):
    assert vault.get("../AGENTS") is None
    assert vault.get("a/b") is None
    assert vault.get("a\\b") is None
    assert vault.get("") is None


def test_ingest_warns_on_very_long_lesson(vault: Vault):
    out = memory_ingest(case_id="long", lesson="x" * 5000, vault=vault)
    assert "note: lesson is 5000 chars" in out

    out = memory_ingest(case_id="short", lesson="tiny", vault=vault)
    assert "note: lesson is" not in out
