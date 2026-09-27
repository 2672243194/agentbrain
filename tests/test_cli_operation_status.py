import subprocess
import sys

import pytest

from agentbrain import cli
from agentbrain.vault import Vault


@pytest.fixture
def local_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    return vault


@pytest.mark.parametrize("arguments", [
    ["query", ""],
    ["ingest", "--lesson", ""],
    ["ingest", "--lesson", "password: SyntheticCredentialForTests123"],
    ["suggest", "--title", "", "--change", "A preference"],
    ["suggest", "--title", "Preference", "--change", ""],
    ["suggest", "--title", "Credential", "--change", "password: SyntheticCredentialForTests123"],
    ["read", *[f"missing-{i}" for i in range(11)]],
])
def test_refused_operations_return_nonzero_without_saving(local_vault, capsys, arguments):
    assert cli.main(["--vault", str(local_vault.root), *arguments]) == 2
    assert capsys.readouterr().out.startswith("Refused:")
    assert list(local_vault.root.rglob("*.md")) == []


def test_read_all_missing_returns_error(local_vault, capsys):
    assert cli.main(["--vault", str(local_vault.root), "read", "missing"]) == 2
    assert capsys.readouterr().out.startswith("Not found:")


def test_partial_read_reports_partial_status_and_counts_once(local_vault, capsys):
    path = local_vault.learnings_dir / "example.md"
    path.write_text("---\ncase_id: example\nuse_count: 0\n---\nSelected text\n", encoding="utf-8")
    assert cli.main(["--vault", str(local_vault.root), "read", "example", "example", "missing"]) == 1
    output = capsys.readouterr().out
    assert output.count("Selected text") == 1
    assert "Not found: missing" in output
    assert local_vault.get("example").use_count == 1


def test_lesson_text_does_not_control_read_exit_status(local_vault, capsys):
    path = local_vault.learnings_dir / "example.md"
    path.write_text("---\ncase_id: example\n---\nNot found: a sample diagnostic\nRefused: example\n", encoding="utf-8")
    assert cli.main(["--vault", str(local_vault.root), "read", "example"]) == 0
    assert "Not found: a sample diagnostic" in capsys.readouterr().out


def test_empty_query_exit_status_reaches_shell(local_vault):
    result = subprocess.run(
        [sys.executable, "-I", "-m", "agentbrain", "--vault", str(local_vault.root), "query", ""],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 2
    assert result.stdout.startswith("Refused:")


def test_query_without_matches_is_successful(local_vault, capsys):
    assert cli.main(["--vault", str(local_vault.root), "query", "unknown topic"]) == 0
    assert "No lessons matched" in capsys.readouterr().out
