from pathlib import Path

import pytest

from agentbrain import rules


# Keep the exact previously shipped text: migration must recognize installed
# rules independently of how the current LEGACY_BLOCKS list is maintained.
PREVIOUS_RULE_BLOCK = """## agentbrain memory discipline

- At task start: call `memory_query` (top_k=5) with the task topic, then call
  `memory_read` for the top 1-3 relevant ids before starting work.
- Mid-task: call `memory_query` again whenever a new subtask, an error or an
  unfamiliar topic appears — a stored lesson may already hold the fix. Plain
  continuation of the same topic needs no re-query. No match? Retry once with
  broader keywords or the other language before concluding nothing is stored.
- When the task teaches something reusable (pitfall, working approach,
  corrected assumption), call `memory_ingest` yourself, immediately — no user
  approval needed. One lesson = one file: facts + applicable scenario + fix,
  <= 30 lines, no storytelling. Sessions end abruptly; waiting loses lessons.
- Never write secrets, tokens or passwords into the vault (ingest blocks
  credential-shaped input; reference secrets as `${ENV:VAR_NAME}`).
"""


@pytest.mark.parametrize("agent", ["claude", "codex", "trae", "cursor", "agentsmd"])
def test_previous_read_flow_upgrade_preserves_surrounding_content_and_is_idempotent(
    tmp_path: Path, agent: str
):
    target = rules.TARGETS[agent]
    path = tmp_path / target.relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\ndescription: agentbrain memory discipline\nalwaysApply: true\n---\n"
        if agent == "cursor"
        else ""
    )
    prefix = frontmatter + "# Owner rules\n\n- Keep the local deployment path.\n\n"
    suffix = "## Deployment\n\n- Ask before publishing.\n"
    path.write_text(prefix + PREVIOUS_RULE_BLOCK + suffix, encoding="utf-8")

    assert "Updated outdated" in rules.write(agent, tmp_path)
    assert path.read_text(encoding="utf-8") == prefix + rules.RULE_BLOCK + suffix
    upgraded_bytes = path.read_bytes()
    assert "Already present and current" in rules.write(agent, tmp_path)
    assert path.read_bytes() == upgraded_bytes


@pytest.mark.parametrize("base_block", [PREVIOUS_RULE_BLOCK, rules.RULE_BLOCK])
def test_read_flow_upgrade_preserves_customized_block(tmp_path: Path, base_block: str):
    path = tmp_path / "AGENTS.md"
    custom = base_block.replace("top_k=5", "top_k=3")
    original = "# Owner rules\n\nKeep this preface.\n\n" + custom + "## Local\n\nKeep this tail.\n"
    path.write_text(original, encoding="utf-8")
    original_bytes = path.read_bytes()

    assert "customized" in rules.write("codex", tmp_path)
    assert path.read_bytes() == original_bytes
