import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbrain import doctor as doctor_module
from agentbrain.doctor import _mcp_hint


def _configuration(vault_root):
    hint = "\n".join(_mcp_hint(str(vault_root)))
    return json.loads(hint.split("```json\n", 1)[1].split("\n```", 1)[0])


def _state(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        if path.is_file() else None
        for path in root.rglob("*")
    }


@pytest.mark.parametrize("isolated", [False, True])
def test_doctor_configuration_preserves_mode_and_unicode_paths(tmp_path, monkeypatch, isolated):
    interpreter = tmp_path / "Python 环境" / "python.exe"
    vault = tmp_path / "记忆 库"
    monkeypatch.setattr(doctor_module, "sys", SimpleNamespace(
        executable=str(interpreter), flags=SimpleNamespace(isolated=isolated),
    ))

    server = _configuration(vault)["mcpServers"]["agentbrain"]

    assert server["command"] == str(interpreter)
    assert Path(server["command"]).is_absolute()
    assert server["args"] == (["-I"] if isolated else []) + ["-m", "agentbrain", "serve"]
    assert server["env"] == {"AGENTBRAIN_VAULT": str(vault)}


@pytest.mark.parametrize("initialized", [False, True])
def test_generated_isolated_command_initializes_outside_project_without_path(
    tmp_path, monkeypatch, initialized
):
    monkeypatch.setattr(doctor_module, "sys", SimpleNamespace(
        executable=sys.executable, flags=SimpleNamespace(isolated=True),
    ))
    cwd = tmp_path / "桌面 工作目录"
    cwd.mkdir()
    (cwd / "agentbrain.py").write_text(
        "raise RuntimeError('Working directory shadowed installed agentbrain')\n",
        encoding="utf-8",
    )
    wrong_pythonpath = tmp_path / "wrong-environment"
    (wrong_pythonpath / "agentbrain").mkdir(parents=True)
    (wrong_pythonpath / "agentbrain" / "__init__.py").write_text(
        "raise RuntimeError('PYTHONPATH shadowed installed agentbrain')\n",
        encoding="utf-8",
    )
    wrong_path = tmp_path / "wrong-path"
    wrong_path.mkdir()
    vault = tmp_path / "临时 记忆库"
    if initialized:
        lessons = vault / "Case-Learnings" / "Learnings"
        lessons.mkdir(parents=True)
        (lessons / "example.md").write_text(
            "---\ncase_id: example\nuse_count: 7\n---\n桌面经验\n",
            encoding="utf-8",
        )
    before = _state(vault)
    server = _configuration(vault)["mcpServers"]["agentbrain"]
    env = dict(
        os.environ,
        PATH=str(wrong_path),
        PYTHONPATH=str(wrong_pythonpath),
        PYTHONIOENCODING="ascii",
    )
    env.update(server["env"])

    with tempfile.TemporaryFile() as stderr, subprocess.Popen(
        [server["command"], *server["args"]],
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        encoding="utf-8",
    ) as process, ThreadPoolExecutor(max_workers=1) as reader:
        try:
            request = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "桌面验证", "version": "0"},
                },
            }
            process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            process.stdin.flush()
            response = json.loads(reader.submit(process.stdout.readline).result(timeout=25))
            assert response["id"] == 1
            assert "error" not in response, response
            assert response["result"]["serverInfo"]["name"] == "agentbrain"
            process.stdin.write(
                '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            )
            process.stdin.flush()
            process.stdin.close()
            process.wait(timeout=25)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        stderr.seek(0)
        assert process.returncode == 0, stderr.read().decode("utf-8", errors="replace")

    assert _state(vault) == before
    assert vault.exists() == initialized
