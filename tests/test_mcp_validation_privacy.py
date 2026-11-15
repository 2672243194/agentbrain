"""Tool schema failures preserve privacy and allow connection reuse."""

import asyncio

import pytest

from agentbrain import mcp_server
from agentbrain.vault import Vault
from test_mcp_feedback import call, markdown_state, stdio


def test_stdio_invalid_argument_shapes_do_not_echo_sensitive_values(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    (vault.learnings_dir / "example.md").write_text(
        "---\ncase_id: example\nuse_count: 0\n---\nCheck the migration.\n", encoding="utf-8",
    )
    synthetic = "SyntheticValidationSecret98765"
    sensitive = {"password": synthetic}
    entry = {
        "lesson_id": "example", "lesson_version": vault.get("example").version,
        "outcome": "helpful", "environment": "Local test",
        "evidence": "The migration check identified the missing table.",
    }
    feedback_calls = [
        {"task_id": sensitive, "entries": [entry]},
        {"task_id": "task", "entries": sensitive},
        {"task_id": "task", "entries": [sensitive]},
        {"entries": [entry], "password": synthetic},
        {"task_id": "task", "password": synthetic},
    ]
    feedback_calls.extend(
        {"task_id": "task", "entries": [dict(entry, **{field: sensitive})]}
        for field in entry
    )
    malformed = [("memory_feedback", arguments) for arguments in feedback_calls]
    malformed.extend([
        ("memory_query", {"query": sensitive}),
        ("memory_read", {"lesson_ids": sensitive}),
        ("memory_read", {"lesson_ids": [sensitive]}),
        ("memory_ingest", {"case_id": sensitive, "lesson": "Check the migration."}),
    ])
    before = markdown_state(vault.root)
    diagnostics = []
    with stdio(vault.root, tmp_path, diagnostics=diagnostics) as (request, _initialized):
        tools = {tool["name"]: tool for tool in request("tools/list")["tools"]}
        assert set(tools["memory_feedback"]["inputSchema"]["properties"]) == {"task_id", "entries"}
        assert set(tools["memory_query"]["inputSchema"]["properties"]) == {"query", "top_k", "mode", "tag"}
        for name, arguments in malformed:
            output = call(request, name, arguments, error=True)
            assert synthetic not in output
            assert "inputSchema" in output
            assert markdown_state(vault.root) == before
        assert "empty query" in call(request, "memory_query", {"query": ""}, error=True)
        assert markdown_state(vault.root) == before
        assert "[example]" in call(request, "memory_query", {"query": "migration"})
        call(request, "memory_feedback", {"task_id": "task", "entries": [entry]})
        assert "helpful: 1" in call(request, "memory_stats", {})
        assert vault.get("example").use_count == 0
    assert diagnostics and all(synthetic not in output for output in diagnostics)


def test_non_validation_tool_errors_keep_their_message(monkeypatch):
    async def failed_call(*args, **kwargs):
        try:
            raise ValueError("Internal status")
        except ValueError as exc:
            raise mcp_server.ToolError("Expected business refusal") from exc

    monkeypatch.setattr(mcp_server._Server, "call_tool", failed_call)
    with pytest.raises(mcp_server.ToolError, match="Expected business refusal"):
        asyncio.run(mcp_server.mcp.call_tool("memory_query", {"query": "test"}))
