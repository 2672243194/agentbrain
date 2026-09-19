"""Keep CLI vault selection and template upgrades confined to their target."""
from __future__ import annotations

from contextlib import contextmanager
from types import ModuleType

import pytest

from agentbrain import cli, rules, scaffold
from agentbrain.config import Config, ENV_VAR
from agentbrain.vault import Vault


@pytest.mark.parametrize("server_fails", [False, True])
def test_serve_honors_explicit_vault_and_restores_environment(tmp_path, monkeypatch, server_fails):
    import agentbrain

    default = tmp_path / "default-vault"
    selected = tmp_path / "selected-vault"
    monkeypatch.setenv(ENV_VAR, str(default))
    opened = []

    def run_server():
        opened.append(Config.load().vault_dir)
        if server_fails:
            raise RuntimeError("server failed")

    server = ModuleType("agentbrain.mcp_server")
    server.main = run_server
    monkeypatch.setattr(agentbrain, "mcp_server", server, raising=False)
    if server_fails:
        with pytest.raises(RuntimeError, match="server failed"):
            cli.main(["--vault", str(selected), "serve"])
    else:
        assert cli.main(["--vault", str(selected), "serve"]) == 0
    assert opened == [selected.resolve()]
    assert Config.load().vault_dir == default.resolve()
    assert not default.exists()
    assert not selected.exists()


def test_missing_doctor_target_does_not_inspect_default_vault(tmp_path, monkeypatch, capsys):
    import agentbrain.doctor as doctor_module

    target = tmp_path / "missing-vault"
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "default-vault"))
    checked = []
    monkeypatch.setattr(doctor_module, "doctor", lambda *args: checked.append(args) or "healthy")
    assert cli.main(["--vault", str(target), "doctor"]) == 2
    assert checked == []
    output = capsys.readouterr()
    assert str(target) in output.err
    assert "agentbrain init" in output.err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("directory_exists", [False, True])
def test_upgrade_rejects_uninitialized_directory_without_writing(tmp_path, directory_exists):
    root = tmp_path / "not-a-vault"
    if directory_exists:
        root.mkdir()
        (root / "owner.md").write_text("Keep this content.\n", encoding="utf-8")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert "No vault found" in scaffold.upgrade(root)
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
    assert root.exists() == directory_exists


@pytest.mark.parametrize("directory_exists", [False, True])
def test_upgrade_cli_returns_error_for_uninitialized_vault(tmp_path, directory_exists, capsys):
    root = tmp_path / "not-a-vault"
    if directory_exists:
        root.mkdir()
    assert cli.main(["--vault", str(root), "upgrade"]) == 2
    assert str(root) in capsys.readouterr().err
    assert not (root / "AGENTS.md").exists()
    assert not (root / "Case-Learnings").exists()


def test_upgrade_checks_customization_after_obtaining_lock(vault, monkeypatch):
    agents = vault.root / "AGENTS.md"
    agents.write_text(scaffold._tpl(scaffold._LEGACY["AGENTS.md"][0]), encoding="utf-8")
    custom = "# Owner instructions\n\nPreserve the new configuration.\n"

    @contextmanager
    def locked(self):
        agents.write_text(custom, encoding="utf-8")
        yield

    monkeypatch.setattr(Vault, "locked", locked)
    monkeypatch.setattr(Vault, "_snapshot_locked", lambda *args: None)
    assert "[kept]" in scaffold.upgrade(vault.root)
    assert agents.read_text(encoding="utf-8") == custom


def test_verify_reports_unsafe_metadata_without_traceback(vault, monkeypatch, capsys):
    def reject_unsafe_update(self, ids):
        raise ValueError("Cannot safely update last_verified_at")

    monkeypatch.setattr(Vault, "verify", reject_unsafe_update)
    assert cli.main(["--vault", str(vault.root), "verify", "case-demo-lesson-01"]) == 2
    output = capsys.readouterr()
    assert "Cannot safely update last_verified_at" in output.err
    assert "Verified" not in output.out


def test_vault_template_shares_safe_selective_session_guidance():
    template = scaffold._tpl("AGENTS.md")
    assert rules.SESSION_GUIDANCE in template
    assert "Housekeeping only when the owner asks" in template
    assert "MCP access does not require loading the whole index" in template
    assert "Do not hand-write lessons" in template
    for obsolete_rule in ("no owner confirmation needed", "Before answering", "read this FIRST", "weekly"):
        assert obsolete_rule not in template


def test_previous_vault_template_upgrade_is_idempotent(vault, monkeypatch):
    agents = vault.root / "AGENTS.md"
    old_template = scaffold._tpl("legacy/AGENTS-0.6.0.md")
    agents.write_text(old_template, encoding="utf-8")
    protected = {
        path: path.read_bytes()
        for path in vault.root.rglob("*.md")
        if path != agents
    }
    snapshots = []
    monkeypatch.setattr(Vault, "_snapshot_locked", lambda self, message: snapshots.append(message))
    assert scaffold.template_status(vault.root)["AGENTS.md"] == "legacy"
    assert "[updated] AGENTS.md" in scaffold.upgrade(vault.root)
    assert agents.read_text(encoding="utf-8") == scaffold._tpl("AGENTS.md")
    assert all(path.read_bytes() == content for path, content in protected.items())
    after = agents.read_bytes()
    assert "[current] AGENTS.md" in scaffold.upgrade(vault.root)
    assert agents.read_bytes() == after
    assert len(snapshots) == 1


def test_previous_vault_template_with_owner_customization_is_preserved(vault):
    agents = vault.root / "AGENTS.md"
    customized = scaffold._tpl("legacy/AGENTS-0.6.0.md") + "\n## Owner additions\n\nAlways retain this.\n"
    agents.write_text(customized, encoding="utf-8")
    before = agents.read_bytes()
    assert scaffold.template_status(vault.root)["AGENTS.md"] == "custom"
    assert "[kept]" in scaffold.upgrade(vault.root)
    assert agents.read_bytes() == before
