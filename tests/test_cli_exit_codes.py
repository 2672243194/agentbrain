"""Exit-code contract for scripted use of the CLI (v0.4.6 batch)."""
from __future__ import annotations

from agentbrain import cli
from agentbrain.api import memory_ingest
from agentbrain.vault import Vault


def test_lint_exit_codes(vault: Vault):
    assert cli.main(["--vault", str(vault.root), "lint"]) == 0  # clean vault

    for i in (1, 2):
        p = vault.learnings_dir / f"exit-code-lesson-{i:02d}.md"
        p.write_text(
            "---\ncase_id: exit-code\nsource_summary: dup one\ntags: [t]\n---\n\nbody\n",
            encoding="utf-8",
        )
    assert cli.main(["--vault", str(vault.root), "lint"]) == 1  # findings present
    assert cli.main(["--vault", str(vault.root), "lint", "--scope", "bogus"]) == 2


def test_doctor_exit_codes(vault: Vault):
    assert cli.main(["--vault", str(vault.root), "doctor"]) == 0  # healthy

    memory_ingest(case_id="stale-x", lesson="exit code check", tags=["t"], vault=vault)
    text = vault.index_md.read_text(encoding="utf-8")
    vault.index_md.write_text(text.replace("stale-x-lesson-01", "gone"), encoding="utf-8")
    assert cli.main(["--vault", str(vault.root), "doctor"]) == 1  # stale index


def test_doctor_exit_2_when_vault_missing(tmp_path):
    assert cli.main(["--vault", str(tmp_path / "nope"), "doctor"]) == 2
