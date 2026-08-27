"""Emit the agent-side memory discipline block for various agent clients.

The vault's AGENTS.md only reaches agents that already query the vault; most
clients never read it unless told. This module ships the discipline text and
knows where each client wants its rule files, so one command wires any agent
to the vault.
"""

from __future__ import annotations

from pathlib import Path

from .locking import atomic_write

MARKER = "agentbrain memory discipline"

RULE_BLOCK = """## agentbrain memory discipline

- At task start: call `memory_query` (top_k=5) with the task topic; read the
  hits (paths are listed) before starting work.
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

# Blocks shipped by earlier releases; `rules --write` replaces these in place.
LEGACY_BLOCKS: list[str] = [
    """## agentbrain memory discipline

- At task start: call `memory_query` (top_k=5) with the task topic; read the
  hits (paths are listed) before starting work.
- Mid-task: on a new subtask, an error, or a topic switch the initial query did
  not cover, re-query with fresh keywords. Plain continuation of the same topic
  needs no re-query.
- At wrap-up: with user confirmation, `memory_ingest` each distinct reusable
  lesson (facts + applicable scenario + fix, one file each).
- Never write secrets, tokens or passwords into the vault (ingest blocks
  credential-shaped input; reference secrets as `${ENV:VAR_NAME}`).
""",
]

MDC_BLOCK = f"""---
description: {MARKER}
alwaysApply: true
---
{RULE_BLOCK}"""


class Target:
    def __init__(self, name: str, relpath: str, block: str = RULE_BLOCK, home_relpath: str | None = None):
        self.name = name
        self.relpath = relpath
        self.block = block
        # Path relative to the user's home directory for a machine-wide rule,
        # or None when the client has no file-based global rules.
        self.home_relpath = home_relpath


TARGETS: dict[str, Target] = {
    "claude": Target("claude", "CLAUDE.md", home_relpath=".claude/CLAUDE.md"),
    "codex": Target("codex", "AGENTS.md", home_relpath=".codex/AGENTS.md"),
    "trae": Target("trae", ".trae/rules/project_rules.md"),
    "cursor": Target("cursor", ".cursor/rules/agentbrain.mdc", block=MDC_BLOCK),
    # agents.md open standard (https://agents.md) — adopted by OpenCode,
    # Gemini CLI, Amp, Codex and others; one file serves all of them.
    "agentsmd": Target("agentsmd", "AGENTS.md"),
}

GENERIC = Target("generic", "")


def render(agent: str) -> str:
    t = TARGETS.get((agent or "").lower(), GENERIC)
    return t.block


def _find_block(text: str) -> tuple[int, int] | None:
    """Locate our discipline block: from the marker heading to the next
    heading (any level) or EOF. Returns line-index span (start, end)."""
    lines = text.splitlines(keepends=True)
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(f"## {MARKER}"):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("#"):
            end = j
            break
    return start, end


def _norm(s: str) -> str:
    return s.strip()


def write(agent: str, project_root: Path, global_: bool = False) -> str:
    """Write the rule block into the project (or the user's home directory
    when global_). Idempotent via MARKER.

    Existing files are never overwritten — rule files may hold the user's own
    content. When the marker block is present but outdated (it matches a block
    shipped by an earlier release), it is refreshed in place; a block that
    matches no shipped version was customized and is left untouched.
    """
    t = TARGETS.get((agent or "").lower())
    if t is None:
        known = ", ".join(sorted(TARGETS))
        return f"Unknown agent '{agent}'. Known: {known}. Use 'generic' to print the block."
    if global_:
        if t.home_relpath is None:
            return (
                f"{t.name} has no file-based global rules (they live in its settings UI). "
                f"Write per-project instead: agentbrain rules --agent {t.name} --write "
                "(run at the project root)."
            )
        path = Path.home() / t.home_relpath
        where = "global"
    else:
        path = project_root / t.relpath
        where = "project"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, t.block)
        return f"Wrote {MARKER} ({where}) -> {path}"
    existing = path.read_text(encoding="utf-8-sig")
    span = _find_block(existing)
    if span is None:
        atomic_write(path, existing.rstrip("\n") + "\n\n" + t.block)
        return f"Wrote {MARKER} ({where}) -> {path}"
    start, end = span
    lines = existing.splitlines(keepends=True)
    old_block = "".join(lines[start:end])
    if _norm(old_block) == _norm(RULE_BLOCK):
        return f"Already present and current ({where}): {path}"
    if any(_norm(old_block) == _norm(b) for b in LEGACY_BLOCKS):
        head = "".join(lines[:start])
        tail = "".join(lines[end:])
        replacement = RULE_BLOCK if tail.strip() else RULE_BLOCK.rstrip("\n") + "\n"
        atomic_write(path, head + replacement + tail)
        return f"Updated outdated {MARKER} block ({where}) -> {path}"
    return (
        f"Block present but customized ({where}): {path} — review and update it by hand "
        f"(current block: `agentbrain rules --agent {t.name}`)"
    )
