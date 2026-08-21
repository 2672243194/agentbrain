"""Regression tests for round-3 bug fixes (v0.3.2)."""
from __future__ import annotations

from agentbrain.api import memory_ingest, memory_lint, memory_suggest
from agentbrain.frontmatter import parse
from agentbrain.vault import Vault


def test_suggest_title_yaml_injection(vault: Vault):
    """A title containing newlines/colons must not corrupt the frontmatter."""
    nasty = "偏好: 更简洁\nhacked: yes"
    out = memory_suggest(nasty, "change body text", vault=vault)
    path = vault.root / out.split("→ ")[1].splitlines()[0]
    meta, body = parse(path.read_text(encoding="utf-8"))
    assert meta["title"] == nasty  # round-trips as ONE scalar
    assert "hacked" not in meta
    assert body.strip() == "change body text"


def test_lint_tag_scope_no_dangling_false_positive(vault: Vault):
    """A supersede target outside the tag scope must not read as DANGLING."""
    memory_ingest(case_id="a", lesson="lesson a body", tags=["x"], vault=vault)
    memory_ingest(case_id="b", lesson="lesson b body", tags=["y"], vault=vault)
    a = vault.get("a-lesson-01")
    a.superseded_by = "b-lesson-01"
    vault.save(a)
    out = memory_lint(scope="tag:x", vault=vault)
    assert "DANGLING" not in out  # b exists, just outside the scope

    a.superseded_by = "missing-lesson-99"  # a真悬空引用仍要报
    vault.save(a)
    out = memory_lint(scope="tag:x", vault=vault)
    assert "DANGLING a-lesson-01" in out


def test_next_lesson_id_glob_metachars(vault: Vault):
    """case_id containing glob metacharacters must not cause id collisions."""
    vault.learnings_dir.joinpath("we[ird-lesson-01.md").write_text(
        "---\ncase_id: we[ird\ntags: []\n---\n\nbody\n", encoding="utf-8"
    )
    assert vault.next_lesson_id("we[ird") == "we[ird-lesson-02"


def test_suggestion_files_are_valid_yaml(vault: Vault):
    for title in ("normal title", "colons: and: colons", "中文标题"):
        memory_suggest(title, "body", vault=vault)
    for p in (vault.root / "Agent-Profile" / "_suggestions").glob("*.md"):
        if p.name.lower() == "readme.md":
            continue
        meta, _ = parse(p.read_text(encoding="utf-8"))
        assert meta.get("status") == "pending"
        assert meta.get("title")
