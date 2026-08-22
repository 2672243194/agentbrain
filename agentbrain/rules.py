"""Emit the agent-side memory discipline block for various agent clients.

The vault's AGENTS.md only reaches agents that already query the vault; most
clients never read it unless told. This module ships the discipline text and
knows where each client wants its rule files, so one command wires any agent
to the vault.
"""

from __future__ import annotations

from pathlib import Path

MARKER = "agentbrain memory discipline"

RULE_BLOCK = """## agentbrain memory discipline

- At task start: call `memory_query` (top_k=5) with the task topic; read the
  hits (paths are listed) before starting work.
- Mid-task: on a new subtask, an error, or a topic switch the initial query did
  not cover, re-query with fresh keywords. Plain continuation of the same topic
  needs no re-query.
- At wrap-up: with user confirmation, `memory_ingest` each distinct reusable
  lesson (facts + applicable scenario + fix, one file each).
- Never write secrets, tokens or passwords into the vault (ingest blocks
  credential-shaped input; reference secrets as `${ENV:VAR_NAME}`).
"""

MDC_BLOCK = f"""---
description: {MARKER}
alwaysApply: true
---
{RULE_BLOCK}"""


class Target:
    def __init__(self, name: str, relpath: str, block: str = RULE_BLOCK):
        self.name = name
        self.relpath = relpath
        self.block = block


TARGETS: dict[str, Target] = {
    "claude": Target("claude", "CLAUDE.md"),
    "codex": Target("codex", "AGENTS.md"),
    "trae": Target("trae", ".trae/rules/project_rules.md"),
    "cursor": Target("cursor", ".cursor/rules/agentbrain.mdc", block=MDC_BLOCK),
}

GENERIC = Target("generic", "")


def render(agent: str) -> str:
    t = TARGETS.get((agent or "").lower(), GENERIC)
    return t.block


def write(agent: str, project_root: Path) -> str:
    """Write the rule block into the project. Idempotent via MARKER.

    Existing files are never overwritten — rule files may hold the user's own
    content, so the block is appended when the marker is absent.
    """
    t = TARGETS.get((agent or "").lower())
    if t is None:
        known = ", ".join(sorted(TARGETS))
        return f"Unknown agent '{agent}'. Known: {known}. Use 'generic' to print the block."
    path = project_root / t.relpath
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if MARKER in existing:
            return f"Already present: {path} (marker found, nothing written)"
        path.write_text(existing.rstrip("\n") + "\n\n" + t.block, encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(t.block, encoding="utf-8")
    return f"Wrote {MARKER} -> {path}"
