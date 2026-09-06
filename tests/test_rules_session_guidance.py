"""Keep the session workflow compact and upgrade shipped rules safely."""

from pathlib import Path

import pytest

from agentbrain import rules


# Exact previous workspace block: migration must recognize already-installed
# instructions independently of the evolving LEGACY_BLOCKS constant.
PREVIOUS_RULE_BLOCK = """## agentbrain memory discipline

- At task start: call `memory_query` (top_k=5) with the task topic. Query again
  for a new subtask, error or unfamiliar topic that earlier results do not cover.
- After each query: call `memory_read` for 1-3 relevant ids not yet read in
  this session before working; search hits are candidates, not full lessons.
- Apply a lesson only when its preconditions fit the current task. Check
  environment-specific and time-sensitive assumptions against current evidence.
- For the same topic, reuse lessons already read; avoid repeated query/read.
  No match? Retry once with broader keywords or the other language before
  concluding nothing is stored.
- When the task teaches something reusable (pitfall, working approach,
  corrected assumption), call `memory_ingest` yourself, immediately — no user
  approval needed. One lesson = one file: facts + applicable scenario + fix,
  <= 30 lines, no storytelling. Sessions end abruptly; waiting loses lessons.
- Never write secrets, tokens or passwords into the vault (ingest blocks
  credential-shaped input; reference secrets as `${ENV:VAR_NAME}`).
"""


def test_session_guidance_keeps_authorization_and_safe_learning_conditions():
    text = " ".join(rules.SESSION_GUIDANCE.split())
    assert "host authorization rules for memory reads and writes" in text
    assert "verified, reusable" in text
    assert "read suspected matches" in text
    assert "Never store guesses, transcripts, secrets" in text
    assert "Personal preferences go only through `memory_suggest`" in text
    assert "Immutable is read-only" in text
    assert "no user approval needed" not in text


def test_session_guidance_is_compact_and_shared_by_all_client_rules():
    assert len(rules.SESSION_GUIDANCE.split()) <= 250
    assert rules.RULE_BLOCK == f"## {rules.MARKER}\n\n{rules.SESSION_GUIDANCE}"
    for agent in ["generic", *rules.TARGETS]:
        assert rules.SESSION_GUIDANCE in rules.render(agent)


@pytest.mark.parametrize("agent", ["claude", "codex", "trae", "cursor", "agentsmd"])
def test_previous_workspace_rules_upgrade_preserves_other_sections(tmp_path: Path, agent: str):
    target = rules.TARGETS[agent]
    path = tmp_path / target.relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = (
        "---\ndescription: agentbrain memory discipline\nalwaysApply: true\n---\n"
        if agent == "cursor"
        else "# Project instructions\n\nKeep this text.\n\n"
    )
    suffix = "## Local workflow\n\nRun the project tests.\n"
    path.write_text(prefix + PREVIOUS_RULE_BLOCK + suffix, encoding="utf-8")

    assert "Updated outdated" in rules.write(agent, tmp_path)
    assert path.read_text(encoding="utf-8") == prefix + rules.RULE_BLOCK + suffix
    upgraded = path.read_bytes()
    assert "Already present" in rules.write(agent, tmp_path)
    assert path.read_bytes() == upgraded


@pytest.mark.parametrize("base_block", [PREVIOUS_RULE_BLOCK, rules.RULE_BLOCK])
def test_session_guidance_upgrade_keeps_customized_block(tmp_path: Path, base_block: str):
    path = tmp_path / "AGENTS.md"
    customized = base_block.replace("top_k=5", "top_k=2")
    path.write_text(customized, encoding="utf-8")
    before = path.read_bytes()
    assert "customized" in rules.write("codex", tmp_path)
    assert path.read_bytes() == before
