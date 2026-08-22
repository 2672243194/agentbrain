from pathlib import Path

from agentbrain import rules


def test_render_generic_block():
    block = rules.render("generic")
    assert rules.MARKER in block
    assert "memory_query" in block
    assert "memory_ingest" in block
    assert "${ENV:VAR_NAME}" in block


def test_render_cursor_uses_mdc_frontmatter():
    block = rules.render("cursor")
    assert block.startswith("---")
    assert "alwaysApply: true" in block
    assert "memory_query" in block


def test_render_unknown_agent_falls_back_to_generic():
    assert rules.render("no-such-agent") == rules.render("generic")


def test_write_trae_creates_rule_file(tmp_path: Path):
    out = rules.write("trae", tmp_path)
    path = tmp_path / ".trae" / "rules" / "project_rules.md"
    assert path.is_file()
    assert rules.MARKER in path.read_text(encoding="utf-8")
    assert "Wrote" in out


def test_write_is_idempotent(tmp_path: Path):
    rules.write("trae", tmp_path)
    first = (tmp_path / ".trae" / "rules" / "project_rules.md").read_text(encoding="utf-8")
    out = rules.write("trae", tmp_path)
    second = (tmp_path / ".trae" / "rules" / "project_rules.md").read_text(encoding="utf-8")
    assert "Already present" in out
    assert first == second


def test_write_never_overwrites_existing_user_rules(tmp_path: Path):
    path = tmp_path / ".trae" / "rules" / "project_rules.md"
    path.parent.mkdir(parents=True)
    path.write_text("# My own project rules\n\n- Run tests before push.\n", encoding="utf-8")
    rules.write("trae", tmp_path)
    merged = path.read_text(encoding="utf-8")
    assert merged.startswith("# My own project rules")
    assert "Run tests before push." in merged
    assert rules.MARKER in merged


def test_write_claude_appends_to_existing_file(tmp_path: Path):
    existing = tmp_path / "CLAUDE.md"
    existing.write_text("# Project instructions\n\nBe terse.\n", encoding="utf-8")
    rules.write("claude", tmp_path)
    merged = existing.read_text(encoding="utf-8")
    assert merged.startswith("# Project instructions")
    assert "Be terse." in merged
    assert rules.MARKER in merged
    rules.write("claude", tmp_path)  # second run must not duplicate
    again = existing.read_text(encoding="utf-8")
    assert again.count(rules.MARKER) == 1


def test_write_unknown_agent_reports_known_names(tmp_path: Path):
    out = rules.write("vscode", tmp_path)
    assert "Unknown agent" in out
    assert "trae" in out
    assert not (tmp_path / "CLAUDE.md").exists()
