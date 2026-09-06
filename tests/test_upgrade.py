"""Upgrade path: refreshing templates and rule blocks shipped by older releases."""
from __future__ import annotations

from pathlib import Path

from agentbrain import scaffold
from agentbrain import rules as rules_mod
from agentbrain.doctor import doctor
from agentbrain.vault import Vault

_LEGACY_DIR = scaffold._TEMPLATES / "legacy"


def _legacy_agents(version: str) -> str:
    return (_LEGACY_DIR / f"AGENTS-{version}.md").read_text(encoding="utf-8")


def test_template_status_classifications(tmp_path):
    scaffold.init(tmp_path)
    assert scaffold.template_status(tmp_path) == {"AGENTS.md": "current", "ONBOARDING.md": "current"}

    (tmp_path / "AGENTS.md").write_text(_legacy_agents("0.4.3"), encoding="utf-8")
    assert scaffold.template_status(tmp_path)["AGENTS.md"] == "legacy"

    (tmp_path / "AGENTS.md").write_text(_legacy_agents("0.4.1"), encoding="utf-8")
    assert scaffold.template_status(tmp_path)["AGENTS.md"] == "legacy"

    custom = scaffold._tpl("AGENTS.md") + "\n## My additions\n\n- custom rule\n"
    (tmp_path / "AGENTS.md").write_text(custom, encoding="utf-8")
    assert scaffold.template_status(tmp_path)["AGENTS.md"] == "custom"

    (tmp_path / "ONBOARDING.md").unlink()
    assert scaffold.template_status(tmp_path)["ONBOARDING.md"] == "missing"


def test_upgrade_refreshes_legacy_template(tmp_path):
    scaffold.init(tmp_path)
    (tmp_path / "AGENTS.md").write_text(_legacy_agents("0.4.3"), encoding="utf-8")
    out = scaffold.upgrade(tmp_path)
    assert "[updated] AGENTS.md" in out
    assert "[current] ONBOARDING.md" in out
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == scaffold._tpl("AGENTS.md")
    # second run is a no-op
    assert "[current] AGENTS.md" in scaffold.upgrade(tmp_path)


def test_upgrade_creates_missing_onboarding(tmp_path):
    scaffold.init(tmp_path)
    (tmp_path / "ONBOARDING.md").unlink()
    out = scaffold.upgrade(tmp_path)
    assert "[created] ONBOARDING.md" in out
    assert (tmp_path / "ONBOARDING.md").read_text(encoding="utf-8") == scaffold._tpl("ONBOARDING.md")


def test_upgrade_keeps_customized_template(tmp_path):
    scaffold.init(tmp_path)
    custom = scaffold._tpl("AGENTS.md") + "\n## My additions\n\n- custom rule\n"
    (tmp_path / "AGENTS.md").write_text(custom, encoding="utf-8")
    out = scaffold.upgrade(tmp_path)
    assert "[kept]" in out
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == custom


def test_upgrade_reports_missing_vault(tmp_path):
    out = scaffold.upgrade(tmp_path / "nope")
    assert "No vault found" in out


def test_doctor_flags_outdated_templates(tmp_path):
    scaffold.init(tmp_path)
    (tmp_path / "AGENTS.md").write_text(_legacy_agents("0.4.1"), encoding="utf-8")
    out = doctor(Vault(tmp_path))
    assert "templates: OUTDATED" in out
    assert "agentbrain upgrade" in out
    scaffold.upgrade(tmp_path)
    assert "OUTDATED" not in doctor(Vault(tmp_path))


def _claude(tmp_path: Path) -> Path:
    return tmp_path / "CLAUDE.md"


def test_rules_write_refreshes_outdated_block(tmp_path):
    p = _claude(tmp_path)
    p.write_text(
        "# My rules\n\nMy own bullet.\n\n" + rules_mod.LEGACY_BLOCKS[0], encoding="utf-8"
    )
    out = rules_mod.write("claude", tmp_path)
    assert "Updated outdated" in out
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# My rules")
    assert "My own bullet." in text
    assert rules_mod.RULE_BLOCK.strip() in text
    assert "with user confirmation" not in text


def test_rules_write_refresh_preserves_trailing_sections(tmp_path):
    p = _claude(tmp_path)
    p.write_text(
        "# My rules\n\n"
        + rules_mod.LEGACY_BLOCKS[0]
        + "\n## My own section\n\n- custom bullet\n",
        encoding="utf-8",
    )
    out = rules_mod.write("claude", tmp_path)
    assert "Updated outdated" in out
    text = p.read_text(encoding="utf-8")
    assert "## My own section" in text
    assert "- custom bullet" in text
    assert text.index("## agentbrain memory discipline") < text.index("## My own section")
    assert "host authorization rules" in " ".join(text.split())


def test_rules_write_current_block_is_noop(tmp_path):
    p = _claude(tmp_path)
    p.write_text(rules_mod.RULE_BLOCK, encoding="utf-8")
    out = rules_mod.write("claude", tmp_path)
    assert "Already present and current" in out
    assert p.read_text(encoding="utf-8") == rules_mod.RULE_BLOCK


def test_rules_write_keeps_customized_block(tmp_path):
    p = _claude(tmp_path)
    custom = rules_mod.RULE_BLOCK.replace("top_k=5", "top_k=3")
    p.write_text(custom, encoding="utf-8")
    out = rules_mod.write("claude", tmp_path)
    assert "customized" in out
    assert p.read_text(encoding="utf-8") == custom


def test_rules_write_refreshes_mdc_block(tmp_path):
    p = tmp_path / ".cursor" / "rules" / "agentbrain.mdc"
    p.parent.mkdir(parents=True)
    p.write_text(
        "---\ndescription: agentbrain memory discipline\nalwaysApply: true\n---\n"
        + rules_mod.LEGACY_BLOCKS[0],
        encoding="utf-8",
    )
    out = rules_mod.write("cursor", tmp_path)
    assert "Updated outdated" in out
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "host authorization rules" in " ".join(text.split())
    assert "with user confirmation" not in text
