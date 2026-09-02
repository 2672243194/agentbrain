"""Exit-code contract for scripted use of the CLI (v0.4.6 batch)."""
from __future__ import annotations

from subprocess import CompletedProcess

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


def test_read_and_stats_commands(vault: Vault, capsys):
    memory_ingest(case_id="cli-read", lesson="CLI selected content", vault=vault)
    assert cli.main(["--vault", str(vault.root), "read", "cli-read-lesson-01"]) == 0
    assert "CLI selected content" in capsys.readouterr().out
    assert cli.main(["--vault", str(vault.root), "stats"]) == 0
    assert "total recorded reads: 1" in capsys.readouterr().out


def test_install_codex_keeps_existing_mcp(vault: Vault, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: "codex")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "configured", ""),
    )
    monkeypatch.setattr("agentbrain.rules.write", lambda *args, **kwargs: "rules installed")

    result = cli.main(["--vault", str(vault.root), "install", "--agent", "codex"])
    assert result == 0
    out = capsys.readouterr().out
    assert "existing entry kept" in out
    assert "rules installed" in out
