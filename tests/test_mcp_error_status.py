import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from agentbrain.vault import Vault


@contextmanager
def _stdio_session(root, cwd):
    """Exercise the public stdio entry point with one persistent connection."""
    with tempfile.TemporaryFile() as stderr, subprocess.Popen(
        [sys.executable, "-I", "-m", "agentbrain", "serve"],
        env=dict(os.environ, AGENTBRAIN_VAULT=str(root)),
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        encoding="utf-8",
    ) as process, ThreadPoolExecutor(max_workers=1) as reader:
        request_id = 0

        def request(method, params=None, *, notification=False):
            nonlocal request_id
            message = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                message["params"] = params
            if not notification:
                request_id += 1
                message["id"] = request_id
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            if notification:
                return None
            while True:
                line = reader.submit(process.stdout.readline).result(timeout=25)
                assert line, "MCP server closed stdout before responding"
                response = json.loads(line)
                if response.get("id") == request_id:
                    assert "error" not in response, response
                    return response["result"]

        try:
            request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agentbrain-error-status-test", "version": "0"},
            })
            request("notifications/initialized", notification=True)
            yield request
            process.stdin.close()
            process.wait(timeout=25)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        stderr.seek(0)
        assert process.returncode == 0, stderr.read().decode("utf-8", errors="replace")


def _call(request, name, arguments, *, error=False):
    result = request("tools/call", {"name": name, "arguments": arguments})
    assert bool(result.get("isError", False)) is error, result
    assert "structuredContent" not in result, result
    content = result["content"]
    assert content and all(block["type"] == "text" for block in content), result
    return "\n".join(block["text"] for block in content)


def _markdown_state(root):
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*.md")
    }


def test_stdio_rejections_preserve_content_and_later_calls_recover(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    lesson_path = vault.learnings_dir / "sample.md"
    lesson_body = "Refused: this is an example diagnostic.\nUNIQUE_DESKTOP_LESSON_BODY"
    lesson_path.write_text(
        "---\ncase_id: sample\nuse_count: 0\n---\n" + lesson_body + "\n",
        encoding="utf-8",
    )
    profile_path = vault.root / "Agent-Profile" / "Immutable" / "rules.md"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text("Refused: an example in the owner's rule.\nPROFILE_BODY", encoding="utf-8")
    before = _markdown_state(vault.root)
    synthetic_credential = "SyntheticCredentialForTests123"
    rejected = [
        ("memory_query", {"query": ""}, "empty query"),
        ("memory_ingest", {"case_id": "empty", "lesson": ""}, "empty lesson"),
        ("memory_ingest", {"case_id": "credential", "lesson": "password: " + synthetic_credential}, "credential"),
        ("memory_suggest", {"title": "", "change": "A preference"}, "Refused:"),
        ("memory_suggest", {"title": "Preference", "change": ""}, "Refused:"),
        ("memory_suggest", {"title": "Credential", "change": "password: " + synthetic_credential}, "credential"),
        ("memory_read", {"lesson_ids": []}, "no lesson ids"),
        ("memory_read", {"lesson_ids": ["sample", *[f"missing-{i}" for i in range(10)]]}, "10 unique"),
        ("memory_read", {"lesson_ids": ["missing"]}, "Not found:"),
        ("memory_lint", {"scope": "unsupported-scope"}, "Invalid scope"),
    ]
    with _stdio_session(vault.root, tmp_path) as request:
        tools = request("tools/list")["tools"]
        assert len(tools) == 8
        assert all(not tool.get("outputSchema") for tool in tools)
        for name, arguments, expected in rejected:
            text = _call(request, name, arguments, error=True)
            assert expected in text, (name, text)
            assert synthetic_credential not in text
            assert "UNIQUE_DESKTOP_LESSON_BODY" not in text
            assert "PROFILE_BODY" not in text
            assert _markdown_state(vault.root) == before
        assert vault.get("sample").use_count == 0
        assert not (vault.root / ".git").exists()
        assert not vault.consolidations_dir.exists()
        assert not (vault.root / "Agent-Profile" / "_suggestions").exists()

        # A failed call must leave the same connection ready for later tools.
        index = _call(request, "memory_query", {"query": "UNIQUE_DESKTOP_LESSON_BODY"})
        assert "[sample]" in index and "mode=index" in index
        assert _markdown_state(vault.root) == before
        profile = _call(request, "memory_profile", {})
        assert "PROFILE_BODY" in profile and "Refused:" in profile
        assert _markdown_state(vault.root) == before

        # Body text is data; its diagnostic-looking words do not signal failure.
        read = _call(request, "memory_read", {"lesson_ids": ["sample", "sample"]})
        assert read.count("UNIQUE_DESKTOP_LESSON_BODY") == 1
        assert "Refused:" in read
        assert vault.get("sample").use_count == 1
        partial = _call(request, "memory_read", {"lesson_ids": ["sample", "missing", "sample"]})
        assert partial.count("UNIQUE_DESKTOP_LESSON_BODY") == 1
        assert "Not found: missing" in partial
        assert vault.get("sample").use_count == 2
        full = _call(request, "memory_query", {"query": "UNIQUE_DESKTOP_LESSON_BODY", "mode": "full"})
        assert full.count("UNIQUE_DESKTOP_LESSON_BODY") == 1
        assert vault.get("sample").use_count == 3
        stats = _call(request, "memory_stats", {})
        assert "total recorded reads: 3" in stats
        no_match = _call(request, "memory_query", {"query": "unrelatedneedle987654"})
        assert "No lessons matched" in no_match
        assert vault.get("sample").use_count == 3
    assert profile_path.read_bytes() == before["Agent-Profile/Immutable/rules.md"][0]


def test_stdio_uninitialized_vault_reports_tool_errors_without_creating_it(tmp_path):
    root = tmp_path / "missing-vault"
    calls = {
        "memory_query": {"query": "desktop"},
        "memory_read": {"lesson_ids": ["missing"]},
        "memory_stats": {},
        "memory_ingest": {"case_id": "desktop", "lesson": "A synthetic verified lesson."},
        "memory_lint": {},
        "memory_distill": {},
        "memory_profile": {},
        "memory_suggest": {"title": "Preference", "change": "A synthetic preference."},
    }
    with _stdio_session(root, tmp_path) as request:
        assert not root.exists()
        for name, arguments in calls.items():
            text = _call(request, name, arguments, error=True)
            assert "vault not found" in text, (name, text)
            assert "agentbrain init" in text
            assert not root.exists()
        assert {tool["name"] for tool in request("tools/list")["tools"]} == calls.keys()
    assert not root.exists()
