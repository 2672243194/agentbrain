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


def test_write_agentsmd_standard_target(tmp_path: Path):
    out = rules.write("agentsmd", tmp_path)
    path = tmp_path / "AGENTS.md"
    assert path.is_file()
    assert rules.MARKER in path.read_text(encoding="utf-8")
    assert "Wrote" in out


def test_write_agentsmd_appends_to_existing_file(tmp_path: Path):
    path = tmp_path / "AGENTS.md"
    path.write_text("# Repo instructions\n\nRun tests.\n", encoding="utf-8")
    rules.write("agentsmd", tmp_path)
    merged = path.read_text(encoding="utf-8")
    assert merged.startswith("# Repo instructions")
    assert "Run tests." in merged
    assert rules.MARKER in merged


def test_write_agentsmd_has_no_global_mode(tmp_path: Path):
    out = rules.write("agentsmd", tmp_path, global_=True)
    assert "no file-based global rules" in out


def test_write_unknown_agent_reports_known_names(tmp_path: Path):
    out = rules.write("vscode", tmp_path)
    assert "Unknown agent" in out
    assert "trae" in out
    assert not (tmp_path / "CLAUDE.md").exists()


def test_write_global_claude_targets_home(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    out = rules.write("claude", tmp_path, global_=True)
    path = tmp_path / ".claude" / "CLAUDE.md"
    assert path.is_file()
    assert "(global)" in out
    assert str(path) in out
    assert rules.MARKER in path.read_text(encoding="utf-8")


def test_write_global_codex_targets_home(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    existing = tmp_path / ".codex" / "AGENTS.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("# Global instructions\n\nBe terse.\n", encoding="utf-8")
    out = rules.write("codex", tmp_path, global_=True)
    merged = existing.read_text(encoding="utf-8")
    assert "Be terse." in merged
    assert rules.MARKER in merged
    assert "(global)" in out
    rules.write("codex", tmp_path, global_=True)  # idempotent
    assert existing.read_text(encoding="utf-8") == merged


def test_write_global_refreshes_outdated_block(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    p = tmp_path / ".claude" / "CLAUDE.md"
    p.parent.mkdir(parents=True)
    p.write_text("# Global\n\n" + rules.LEGACY_BLOCKS[0], encoding="utf-8")
    out = rules.write("claude", tmp_path, global_=True)
    assert "Updated outdated" in out
    assert "(global)" in out
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# Global")
    assert "with user confirmation" not in text


def test_write_global_unsupported_agent_explains(tmp_path: Path):
    out = rules.write("trae", tmp_path, global_=True)
    assert "no file-based global rules" in out
    out = rules.write("cursor", tmp_path, global_=True)
    assert "no file-based global rules" in out


def test_write_global_does_not_touch_project_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    rules.write("claude", tmp_path, global_=True)
    assert (tmp_path / "home" / ".claude" / "CLAUDE.md").is_file()
    assert not (tmp_path / "CLAUDE.md").exists()
