import asyncio


def test_mcp_tools_registered():
    from agentbrain import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "memory_query",
        "memory_ingest",
        "memory_lint",
        "memory_distill",
        "memory_profile",
        "memory_suggest",
    }


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


def test_mcp_profile_and_suggest(tmp_path, monkeypatch):
    from agentbrain import mcp_server, scaffold

    root = tmp_path / "vault"
    scaffold.init(root)
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(root))

    assert "[immutable] profile" in mcp_server.memory_profile()

    out = mcp_server.memory_suggest(title="用中文回复", change="Owner prefers Chinese replies.")
    assert "Suggestion saved" in out
    assert "Agent-Profile/_suggestions/" in out


def test_mcp_resources(tmp_path, monkeypatch):
    from agentbrain import mcp_server, scaffold

    root = tmp_path / "vault"
    scaffold.init(root)
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(root))

    async def run():
        resources = await mcp_server.mcp.list_resources()
        uris = {str(r.uri) for r in resources}
        rules = await mcp_server.mcp.read_resource("agentbrain://rules")
        index = await mcp_server.mcp.read_resource("agentbrain://index")
        profile = await mcp_server.mcp.read_resource("agentbrain://profile")
        return uris, rules, index, profile

    uris, rules, index, profile = asyncio.run(run())
    assert uris == {
        "agentbrain://rules",
        "agentbrain://index",
        "agentbrain://profile",
    }
    assert "Session workflow" in rules[0].content
    assert "Case-Learnings Index" in index[0].content
    assert "[immutable] profile" in profile[0].content


def test_mcp_resources_without_vault(tmp_path, monkeypatch):
    from agentbrain import mcp_server

    monkeypatch.setenv("AGENTBRAIN_VAULT", str(tmp_path / "missing"))

    async def run():
        return await mcp_server.mcp.read_resource("agentbrain://index")

    assert "not initialized" in asyncio.run(run())[0].content
