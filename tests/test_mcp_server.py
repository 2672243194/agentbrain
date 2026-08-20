import asyncio


def test_mcp_tools_registered():
    from agentbrain import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"memory_query", "memory_ingest", "memory_lint", "memory_distill"}


def _result_text(result) -> str:
    content = getattr(result, "content", None)
    if content is None:
        content = result[0] if isinstance(result, tuple) else result
    return content[0].text


def test_mcp_tool_call_end_to_end(tmp_path, monkeypatch):
    from agentbrain import mcp_server, scaffold

    root = tmp_path / "vault"
    scaffold.init(root)
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(root))

    result = mcp_server.memory_ingest(
        case_id="c-mcp",
        lesson="MCP 工具调用要处理超时",
        tags=["mcp"],
    )
    assert "Saved c-mcp-lesson-01" in result

    async def call():
        return await mcp_server.mcp.call_tool("memory_query", {"query": "MCP 超时"})

    assert "c-mcp-lesson-01" in _result_text(asyncio.run(call()))
