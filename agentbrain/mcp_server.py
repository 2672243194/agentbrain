from __future__ import annotations

from inspect import signature
import sys

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import api
from .config import Config
from .profile import Profile
from .rules import SESSION_GUIDANCE
from .vault import Vault, VaultNotInitialized

SERVER_INSTRUCTIONS = "Use agentbrain's local Markdown memory for substantive work:\n\n" + SESSION_GUIDANCE

if "instructions" in signature(_Server).parameters:
    mcp = _Server("agentbrain", instructions=SERVER_INSTRUCTIONS)
else:
    mcp = _Server("agentbrain")
    print(
        "agentbrain: this MCP SDK does not support server instructions (available since 1.3.0); "
        "memory tools remain available, but session guidance requires client rules.",
        file=sys.stderr,
    )


def memory_query(
    query: str, top_k: int = 5, mode: str = "index", tag: str | None = None
) -> str:
    """Search active lessons by concrete task/error keywords. mode='index'
    returns compact candidates without counting reads; mode='full' reads and
    counts full text. top_k is clamped to 1-20; tag optionally filters results.
    Expired/superseded lessons are excluded. No match? Retry once with broader
    keywords or the other language."""
    return api.memory_query(query=query, top_k=top_k, mode=mode, tag=tag)


def memory_read(lesson_ids: list[str]) -> str:
    """Read selected lessons in full; pass at most 10 unique ids. Active reads
    count once per id per call. Superseded ids point to replacements; expired
    content is labelled and does not increase usage."""
    return api.memory_read(lesson_ids=lesson_ids)


def memory_stats() -> str:
    """Return compact vault utilization statistics: active, retired, read,
    unread, total reads and the most-read lessons."""
    return api.memory_stats()


def memory_ingest(
    case_id: str,
    lesson: str,
    tags: list[str] | None = None,
    confidence: float = 0.8,
    source_summary: str | None = None,
) -> str:
    """Add a verified, reusable lesson after duplicate checks and host
    authorization. Format: facts + applicable scenario + fix, <= 30 lines;
    source_summary <= 60 chars. Do not save guesses or conversation transcripts.
    Creates a new file only — never edits existing lessons; near-duplicates are
    flagged; credential-shaped content is refused automatically."""
    return api.memory_ingest(
        case_id=case_id,
        lesson=lesson,
        tags=tags,
        confidence=confidence,
        source_summary=source_summary,
    )


def memory_lint(scope: str = "all") -> str:
    """Health-check the vault: duplicates, stale, expired, untagged and
    low-confidence lessons. Writes a merge proposal to _consolidations/
    that a human approves via `agentbrain apply`."""
    return api.memory_lint(scope=scope)


def memory_distill(window_days: int = 30, min_repeat: int = 3) -> str:
    """Find recurring patterns (cases/tags ingested >= min_repeat times within
    window_days) and write a promotion proposal to _consolidations/."""
    return api.memory_distill(window_days=window_days, min_repeat=min_repeat)


def memory_profile() -> str:
    """Read the owner's hard rules (Immutable) and soft preferences
    (Mutable-Hints). The profile is read-only; changes go through memory_suggest."""
    return api.memory_profile()


def memory_suggest(title: str, change: str) -> str:
    """The only agent-writable path toward hard rules (Immutable) and soft
    preferences (Mutable-Hints). Propose a change you observed with a one-line
    rule wording; it lands in Agent-Profile/_suggestions/ for the owner to
    review. The profile itself is never modified by agents."""
    return api.memory_suggest(title=title, change=change)


_text_options = {"structured_output": False} if "structured_output" in signature(mcp.add_tool).parameters else {}
for _tool in (
    memory_query, memory_read, memory_stats, memory_ingest,
    memory_lint, memory_distill, memory_profile, memory_suggest,
):
    mcp.add_tool(_tool, **_text_options)


def _open() -> Vault | None:
    try:
        return Vault.open(Config.load())
    except VaultNotInitialized:
        return None


@mcp.resource("agentbrain://rules", description="Vault rules every agent must follow (AGENTS.md)")
def _rules_resource() -> str:
    v = _open()
    if v is None:
        return "Vault not initialized. Run: agentbrain init"
    p = v.root / "AGENTS.md"
    return p.read_text(encoding="utf-8-sig") if p.is_file() else "AGENTS.md not found."


@mcp.resource("agentbrain://index", description="Lesson index — retrieval layer 1 (Case-Learnings/Index.md)")
def _index_resource() -> str:
    v = _open()
    if v is None:
        return "Vault not initialized. Run: agentbrain init"
    if v.index_md.is_file():
        return v.index_md.read_text(encoding="utf-8-sig")
    return "Index.md not found yet — ingest a lesson first."


@mcp.resource("agentbrain://profile", description="Owner profile: hard rules + soft preferences (read-only)")
def _profile_resource() -> str:
    v = _open()
    if v is None:
        return "Vault not initialized. Run: agentbrain init"
    return Profile(v).read() or "Profile is empty; agents never edit it — propose via memory_suggest."


def main() -> None:
    mcp.run()
