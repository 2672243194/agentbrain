from __future__ import annotations

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import api
from .config import Config
from .profile import Profile
from .vault import Vault, VaultNotInitialized

mcp = _Server("agentbrain")


def memory_query(query: str, top_k: int = 5, mode: str = "index") -> str:
    """Search long-term memory lessons. Call at task start.
    mode='index' (default) returns compact hits: id, summary, tags, path, gist.
    mode='full' additionally returns the full text of the top hits."""
    return api.memory_query(query=query, top_k=top_k, mode=mode)


def memory_ingest(
    case_id: str,
    lesson: str,
    tags: list[str] | None = None,
    confidence: float = 0.8,
    source_summary: str | None = None,
) -> str:
    """Save a reusable lesson to long-term memory. Call when the task revealed
    something worth remembering: facts + applicable scenario + fix, <= 30 lines.
    Creates a new file only — never edits existing lessons."""
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
    """Return the owner profile: hard rules (Agent-Profile/Immutable) and soft
    preferences (Agent-Profile/Mutable-Hints). Read-only. Call once per session
    and tailor tone, language and formatting accordingly."""
    return api.memory_profile()


def memory_suggest(title: str, change: str) -> str:
    """Propose a change to the owner profile (e.g. a preference you observed).
    Writes to Agent-Profile/_suggestions/ for the owner to review — the profile
    itself is never modified by agents."""
    return api.memory_suggest(title=title, change=change)


mcp.add_tool(memory_query)
mcp.add_tool(memory_ingest)
mcp.add_tool(memory_lint)
mcp.add_tool(memory_distill)
mcp.add_tool(memory_profile)
mcp.add_tool(memory_suggest)


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
    return p.read_text(encoding="utf-8") if p.is_file() else "AGENTS.md not found."


@mcp.resource("agentbrain://index", description="Lesson index — retrieval layer 1 (Case-Learnings/Index.md)")
def _index_resource() -> str:
    v = _open()
    if v is None:
        return "Vault not initialized. Run: agentbrain init"
    if v.index_md.is_file():
        return v.index_md.read_text(encoding="utf-8")
    return "Index.md not found yet — ingest a lesson first."


@mcp.resource("agentbrain://profile", description="Owner profile: hard rules + soft preferences (read-only)")
def _profile_resource() -> str:
    v = _open()
    if v is None:
        return "Vault not initialized. Run: agentbrain init"
    return Profile(v).read() or "Profile is empty."


def main() -> None:
    mcp.run()
