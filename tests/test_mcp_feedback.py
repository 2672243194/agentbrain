"""Exercise feedback through real MCP initialization and tool calls."""

import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from agentbrain.vault import Vault


@contextmanager
def stdio(root, cwd):
    with tempfile.TemporaryFile() as stderr, subprocess.Popen(
        [sys.executable, "-I", "-m", "agentbrain", "serve"],
        env=dict(os.environ, AGENTBRAIN_VAULT=str(root)), cwd=cwd,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
        text=True, encoding="utf-8",
    ) as process, ThreadPoolExecutor(max_workers=1) as reader:
        serial = 0

        def request(method, params=None, *, notification=False):
            nonlocal serial
            message = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                message["params"] = params
            if not notification:
                serial += 1
                message["id"] = serial
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            if notification:
                return None
            while True:
                line = reader.submit(process.stdout.readline).result(timeout=25)
                assert line, "MCP server closed stdout before replying"
                response = json.loads(line)
                if response.get("id") == serial:
                    assert "error" not in response, response
                    return response["result"]

        try:
            initialized = request("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "feedback-test", "version": "0"},
            })
            request("notifications/initialized", notification=True)
            yield request, initialized
            process.stdin.close()
            process.wait(timeout=25)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        stderr.seek(0)
        assert process.returncode == 0, stderr.read().decode("utf-8", errors="replace")


def call(request, name, arguments, *, error=False):
    result = request("tools/call", {"name": name, "arguments": arguments})
    assert bool(result.get("isError", False)) is error, result
    assert "structuredContent" not in result
    assert result["content"] and all(block["type"] == "text" for block in result["content"])
    return "\n".join(block["text"] for block in result["content"])


def markdown_state(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*.md")
    }


def test_feedback_stdio_schema_rejection_idempotence_and_later_recovery(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    (vault.learnings_dir / "example.md").write_text(
        "---\ncase_id: migration\nuse_count: 0\n---\nCheck the migration before restart.\n",
        encoding="utf-8",
    )
    initial = markdown_state(vault.root)
    with stdio(vault.root, tmp_path) as (request, initialized):
        assert markdown_state(vault.root) == initial
        assert not (vault.case_dir / "_feedback").exists()
        if initialized.get("instructions"):
            assert "memory_feedback" in initialized["instructions"]
        tools = {tool["name"]: tool for tool in request("tools/list")["tools"]}
        feedback = tools["memory_feedback"]
        assert not feedback.get("outputSchema")
        schema = feedback["inputSchema"]
        assert set(schema["properties"]) == {"task_id", "entries"}
        item_schema = schema["properties"]["entries"]["items"]
        if "$ref" in item_schema:
            path = item_schema["$ref"].removeprefix("#/").split("/")
            item_schema = schema
            for key in path:
                item_schema = item_schema[key]
        assert set(item_schema["properties"]) == {
            "lesson_id", "lesson_version", "outcome", "environment", "evidence",
        }
        assert set(item_schema["required"]) == set(item_schema["properties"])

        # Clients report the version they actually read, not the current version
        # invented at feedback time. Reading is still a separate counter.
        read = call(request, "memory_read", {"lesson_ids": ["example"]})
        version = re.search(r"version: ([0-9a-f]{64})", read).group(1)
        item = {
            "lesson_id": "example", "lesson_version": version, "outcome": "helpful",
            "environment": "Windows / local database",
            "evidence": "The migration check revealed a missing table before restart.",
        }
        before = markdown_state(vault.root)
        synthetic = "SyntheticFeedbackSecret12345"
        rejected = [
            {"task_id": "task-01", "entries": []},
            {"task_id": "task-01", "entries": [dict(item, lesson_version="0" * 64)]},
            {"task_id": "task-01", "entries": [dict(item, outcome="good-enough")]},
            {"task_id": "task-01", "entries": [dict(item, environment=123)]},
            {"task_id": "task-01", "entries": [dict(item, extra="password: " + synthetic)]},
        ]
        rejected.extend(
            {"task_id": "task-01", "entries": [dict(item, **{field: "password: " + synthetic})]}
            for field in item
        )
        rejected.append({"task_id": "password: " + synthetic, "entries": [item]})
        for arguments in rejected:
            output = call(request, "memory_feedback", arguments, error=True)
            assert synthetic not in output
            assert markdown_state(vault.root) == before

        output = call(request, "memory_feedback", {"task_id": "task-01", "entries": [item]})
        assert not output.startswith("Refused:")
        after = markdown_state(vault.root)
        assert {name: after[name] for name in before} == before
        assert len(list((vault.case_dir / "_feedback").glob("*.md"))) == 1
        call(request, "memory_feedback", {"task_id": "task-01", "entries": [item]})
        assert markdown_state(vault.root) == after
        conflict = call(request, "memory_feedback", {
            "task_id": "task-01", "entries": [dict(item, outcome="ineffective")],
        }, error=True)
        assert "Refused:" in conflict
        assert markdown_state(vault.root) == after
        stats = call(request, "memory_stats", {})
        assert re.search(r"\bhelpful\s*:\s*1\b", stats), stats
        assert "total recorded reads: 1" in stats
        assert vault.get("example").use_count == 1
        assert "[example]" in call(request, "memory_query", {"query": "migration"})
        assert markdown_state(vault.root) == after
        assert not (vault.root / ".git").exists()


def test_feedback_stdio_missing_vault_does_not_create_storage(tmp_path):
    root = tmp_path / "uninitialized"
    with stdio(root, tmp_path) as (request, _initialized):
        assert not root.exists()
        assert "memory_feedback" in {tool["name"] for tool in request("tools/list")["tools"]}
        output = call(request, "memory_feedback", {
            "task_id": "task-01",
            "entries": [{
                "lesson_id": "example", "lesson_version": "0" * 64,
                "outcome": "unverified", "environment": "Local test environment",
                "evidence": "Verification has not completed.",
            }],
        }, error=True)
        assert "vault not found" in output
        assert "agentbrain init" in output
        assert not root.exists()
    assert not root.exists()
