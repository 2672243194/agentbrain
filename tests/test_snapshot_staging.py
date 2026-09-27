"""A failed git add must never commit a pre-existing, incomplete index."""
from __future__ import annotations

import subprocess

import pytest

from agentbrain.snapshot import Snapshot


@pytest.mark.parametrize("stage_result", [
    None,
    subprocess.CompletedProcess(["git", "add", "-A"], 1, "", "staging failed"),
])
def test_staging_failure_does_not_attempt_commit(tmp_path, monkeypatch, stage_result):
    (tmp_path / ".git").mkdir()
    snapshot = Snapshot(tmp_path)
    commands = []

    def git(*args):
        commands.append(args)
        return stage_result

    monkeypatch.setattr(snapshot, "_git", git)
    assert snapshot.commit("must not commit").startswith("failed:")
    assert commands == [("add", "-A")]


def test_real_git_add_failure_keeps_head_and_preexisting_index(tmp_path):
    snapshot = Snapshot(tmp_path)
    assert snapshot.ensure()
    note = tmp_path / "note.md"
    note.write_text("baseline", encoding="utf-8")
    assert snapshot.commit("baseline") == "committed"

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True,
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        ).stdout.strip()

    head_before = git("rev-parse", "HEAD")
    note.write_text("old staged change", encoding="utf-8")
    git("add", "note.md")
    note.write_text("newest intended change", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    subprocess.run(["git", "-C", str(nested), "init"], check=True, capture_output=True, timeout=20)

    result = snapshot.commit("incomplete snapshot")
    assert result.startswith("failed: git add:")
    assert git("rev-parse", "HEAD") == head_before
    assert git("show", ":note.md") == "old staged change"
    assert note.read_text(encoding="utf-8") == "newest intended change"
