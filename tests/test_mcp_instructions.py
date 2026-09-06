import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import types
import warnings
from inspect import signature
from pathlib import Path

import pytest
from agentbrain import mcp_server, rules


EXPECTED_INPUTS = {
    "memory_query": {"query", "top_k", "mode", "tag"},
    "memory_read": {"lesson_ids"},
    "memory_stats": set(),
    "memory_ingest": {"case_id", "lesson", "tags", "confidence", "source_summary"},
    "memory_lint": {"scope"},
    "memory_distill": {"window_days", "min_repeat"},
    "memory_profile": set(),
    "memory_suggest": {"title", "change"},
}


@pytest.mark.parametrize(
    "required",
    [
        ("first substantive task", "conversation session", "memory_profile", "once"),
        ("Before substantive work", "memory_query", "concrete task/error keywords"),
        ("memory_read", "1-3 ids", "not yet read this session"),
        ("preconditions", "environment", "time-sensitive", "current evidence"),
        ("Reuse already-read", "new error", "subtask", "earlier results do not cover"),
        ("small talk", "repeated questions", "not once per MCP connection"),
        ("host authorization", "verified, reusable", "memory_ingest", "check duplicates", "read suspected matches"),
        ("Never store guesses, transcripts, secrets", "memory_suggest", "Immutable is read-only"),
    ],
)
def test_server_instructions_cover_the_shared_session_workflow(required):
    text = " ".join(mcp_server.SERVER_INSTRUCTIONS.split())
    assert all(fragment in text for fragment in required)
    assert rules.SESSION_GUIDANCE in mcp_server.SERVER_INSTRUCTIONS
    assert len(text.split()) <= 300


def _state(root):
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        if path.is_file() else None
        for path in root.rglob("*")
    }


BOOTSTRAP = """
from agentbrain import api
from agentbrain.profile import Profile
from agentbrain.vault import Vault
def forbidden(*args, **kwargs):
    raise AssertionError('Initialization must not access or mutate the vault')
Vault.open = classmethod(forbidden)
Vault._read_document = staticmethod(forbidden)
Vault._snapshot_locked = forbidden
Profile.read = forbidden
api.memory_ingest = forbidden
from agentbrain.mcp_server import main
main()
"""


@pytest.mark.parametrize("initialized", [False, True])
def test_stdio_initialize_contains_instructions_without_vault_access(tmp_path, initialized):
    root = tmp_path / "vault"
    if initialized:
        for relative, content in {
            "Case-Learnings/Learnings/example.md": "---\ncase_id: example\nuse_count: 7\n---\nbody\n",
            "Case-Learnings/Index.md": "# Existing index\n",
            "Case-Learnings/log.md": "# Existing log\n",
            "Agent-Profile/Immutable/profile.md": "# Owner rules\n",
        }.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    before = _state(root)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "agentbrain-test", "version": "0"},
        }},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    result = subprocess.run(
        [sys.executable, "-I", "-c", BOOTSTRAP],
        input="".join(json.dumps(request) + "\n" for request in requests),
        env=dict(os.environ, AGENTBRAIN_VAULT=str(root)), cwd=tmp_path,
        capture_output=True, text=True, encoding="utf-8", timeout=25,
    )
    assert result.returncode == 0, result.stderr
    responses = {message["id"]: message for message in map(json.loads, result.stdout.splitlines()) if "id" in message}
    assert "error" not in responses[1], responses[1]
    assert "error" not in responses[2], responses[2]
    if "instructions" in signature(mcp_server._Server).parameters:
        assert responses[1]["result"]["instructions"] == mcp_server.SERVER_INSTRUCTIONS
    else:
        assert not responses[1]["result"].get("instructions")
        assert "does not support server instructions" in result.stderr
    tools = {tool["name"]: tool for tool in responses[2]["result"]["tools"]}
    assert tools.keys() == EXPECTED_INPUTS.keys()
    for name, expected in EXPECTED_INPUTS.items():
        assert set(tools[name]["inputSchema"]["properties"]) == expected
        assert not tools[name].get("outputSchema")
    assert _state(root) == before
    assert root.exists() == initialized


def test_same_server_provides_instructions_to_later_connections(tmp_path, monkeypatch):
    client_module = pytest.importorskip("mcp.client.client")
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(tmp_path / "unused"))

    def forbidden(*args, **kwargs):
        pytest.fail("Connection initialization accessed the vault")

    monkeypatch.setattr(mcp_server.Vault, "open", forbidden)

    async def initialize_twice():
        responses = []
        for _ in range(2):
            async with client_module.Client(mcp_server.mcp, mode="legacy") as client:
                assert client.session.discover_result is None
                responses.append(client.session.initialize_result.instructions)
        return responses

    assert asyncio.run(asyncio.wait_for(initialize_twice(), 20)) == [mcp_server.SERVER_INSTRUCTIONS] * 2
    assert not (tmp_path / "unused").exists()


class ToolServerStub:
    def add_tool(self, function):
        self.tools.append(function)

    def resource(self, uri, **kwargs):
        return lambda function: function


class InstructionsServerStub(ToolServerStub):
    def __init__(self, name, instructions=None):
        self.name, self.instructions, self.tools = name, instructions, []


class SettingsOnlyServerStub(ToolServerStub):
    def __init__(self, name, **settings):
        self.name, self.settings, self.tools = name, settings, []


@pytest.mark.parametrize("branch", ["mcpserver", "fastmcp", "settings_only"])
def test_sdk_import_branches_use_explicit_instructions_support(monkeypatch, capsys, branch):
    modern_module = "mcp.server.mcpserver"
    legacy_module = "mcp.server.fastmcp"
    fake = types.ModuleType(modern_module if branch == "mcpserver" else legacy_module)
    if branch == "mcpserver":
        fake.MCPServer = InstructionsServerStub
        monkeypatch.setitem(sys.modules, modern_module, fake)
    else:
        fake.FastMCP = SettingsOnlyServerStub if branch == "settings_only" else InstructionsServerStub
        monkeypatch.setitem(sys.modules, modern_module, None)
        monkeypatch.setitem(sys.modules, legacy_module, fake)
    spec = importlib.util.spec_from_file_location("agentbrain._instructions_branch", Path(mcp_server.__file__))
    module = importlib.util.module_from_spec(spec)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        spec.loader.exec_module(module)
    if branch == "settings_only":
        assert module.mcp.settings == {}
    else:
        assert module.mcp.instructions == mcp_server.SERVER_INSTRUCTIONS
    assert module.mcp.name == "agentbrain"
    assert {tool.__name__ for tool in module.mcp.tools} == EXPECTED_INPUTS.keys()
    captured = capsys.readouterr()
    assert captured.out == ""
    if branch == "settings_only":
        assert "does not support server instructions" in captured.err
    else:
        assert captured.err == ""
