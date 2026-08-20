from __future__ import annotations

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import api

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
    that requires human approval."""
    return api.memory_lint(scope=scope)


def memory_distill(window_days: int = 30, min_repeat: int = 3) -> str:
    """Find recurring patterns (cases/tags ingested >= min_repeat times within
    window_days) and write a promotion proposal to _consolidations/."""
    return api.memory_distill(window_days=window_days, min_repeat=min_repeat)


mcp.add_tool(memory_query)
mcp.add_tool(memory_ingest)
mcp.add_tool(memory_lint)
mcp.add_tool(memory_distill)


def main() -> None:
    mcp.run()
