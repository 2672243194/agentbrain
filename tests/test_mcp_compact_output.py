import asyncio

from agentbrain import mcp_server
from agentbrain.frontmatter import dump


def test_mcp_returns_one_text_payload_without_duplicate_structured_content(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    lessons = root / "Case-Learnings" / "Learnings"
    lessons.mkdir(parents=True)
    (lessons / "compact-lesson-01.md").write_text(
        dump({"case_id": "compact", "source_summary": "compact result", "tags": ["compact"]}, "compact result"),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(root))

    async def call():
        tools = await mcp_server.mcp.list_tools()
        result = await mcp_server.mcp.call_tool("memory_query", {"query": "compact"})
        return tools, result

    tools, result = asyncio.run(call())
    for tool in tools:
        assert getattr(tool, "output_schema", getattr(tool, "outputSchema", None)) is None
    content = getattr(result, "content", result)
    if isinstance(content, tuple):
        content, structured = content
        assert not structured
    assert not getattr(result, "structured_content", getattr(result, "structuredContent", None))
    assert len(content) == 1
    assert "compact-lesson-01" in content[0].text
