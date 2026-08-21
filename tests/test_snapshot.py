"""Tests for git snapshots and the doctor command (v0.4.0)."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess

from agentbrain.api import memory_ingest, memory_suggest
from agentbrain.apply import apply_proposal
from agentbrain.doctor import doctor
from agentbrain.snapshot import Snapshot
from agentbrain.vault import Vault


def _rmtree(path) -> None:
    def _chmod_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=_chmod_retry)


def _log(root) -> list[str]:
    r = subprocess.run(
        ["git", "-C", str(root), "log", "--pretty=format:%s"],
        capture_output=True, text=True, timeout=20,
    )
    return r.stdout.splitlines()


def test_init_enables_snapshots(tmp_path):
    from agentbrain import scaffold

    root = tmp_path / "vault"
    out = scaffold.init(root)
    assert "Snapshots: enabled" in out
    assert Snapshot(root).enabled
    assert any("init" in m for m in _log(root))
    assert (root / ".gitignore").is_file()
    assert ".vault.lock" in (root / ".gitignore").read_text(encoding="utf-8")


def test_ingest_creates_snapshot_commit(vault: Vault):
    memory_ingest(case_id="snap", lesson="snapshot me", tags=["s"], vault=vault)
    assert any("ingest: snap-lesson" in m for m in _log(vault.root))


def test_suggest_creates_snapshot_commit(vault: Vault):
    memory_suggest("snapshot title", "change", vault=vault)
    assert any(m.startswith("suggest: snapshot title") for m in _log(vault.root))


def test_no_git_repo_graceful(tmp_path):
    """A vault without .git must keep working; snapshot is a no-op."""
    from agentbrain import scaffold

    root = tmp_path / "vault"
    scaffold.init(root)
    _rmtree(root / ".git")
    v = Vault.open(root=root)
    memory_ingest(case_id="nogit", lesson="still works", tags=[], vault=v)
    assert v.get("nogit-lesson-01") is not None
    assert not Snapshot(root).enabled
    assert Snapshot(root).commit("x") is False


def test_git_missing_graceful(vault: Vault, monkeypatch, tmp_path):
    """If git itself is unavailable, init and writes still succeed."""
    import agentbrain.snapshot as snap_mod

    def boom(*a, **k):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(snap_mod.subprocess, "run", boom)
    assert Snapshot(tmp_path / "fresh-vault").ensure() is False
    memory_ingest(case_id="nogit2", lesson="still works", tags=[], vault=vault)
    assert vault.get("nogit2-lesson-01") is not None


def test_snapshot_command_commits_pending(vault: Vault):
    n_before = len(_log(vault.root))
    (vault.learnings_dir / "hand-edit.md").write_text(
        "---\ncase_id: hand\ntags: [h]\n---\n\nedited by hand\n", encoding="utf-8"
    )
    snap = Snapshot(vault.root)
    with vault.locked():
        assert snap.commit("manual snapshot")
    assert len(_log(vault.root)) == n_before + 1
    with vault.locked():  # second run: nothing new
        assert not snap.commit("manual snapshot")


def test_apply_snapshots(vault: Vault):
    memory_ingest(case_id="sa", lesson="lesson one text", tags=["t"], vault=vault)
    memory_ingest(case_id="sb", lesson="lesson two text", tags=["t"], vault=vault)
    a, b = vault.get("sa-lesson-01"), vault.get("sb-lesson-01")
    a.source_summary, b.source_summary = "same summary", "same summary"
    vault.save(a)
    vault.save(b)
    from agentbrain.api import memory_lint

    out = memory_lint(vault=vault)
    proposal = vault.root / out.split("Proposal written: ")[1].splitlines()[0]
    apply_proposal(vault, proposal)
    assert any(m.startswith("apply:") for m in _log(vault.root))


def test_doctor_healthy_report(vault: Vault):
    memory_ingest(case_id="doc", lesson="doctor check", tags=["d"], vault=vault)
    out = doctor(vault)
    assert "agentbrain" in out and "Python" in out
    assert "lessons: 2 active" in out  # demo + doc
    assert "index: fresh" in out
    assert "lock: acquire/release ok" in out
    assert "snapshot: enabled" in out
    assert "Everything looks healthy." in out
    assert '"command": "agentbrain"' in out  # MCP snippet present
    m = re.search(r'"AGENTBRAIN_VAULT": (".*")\s*}', out)
    assert m and json.loads(m.group(1)) == str(vault.root)  # valid, escaped JSON


def test_doctor_detects_stale_index(vault: Vault):
    memory_ingest(case_id="stale", lesson="stale check", tags=["s"], vault=vault)
    text = vault.index_md.read_text(encoding="utf-8")
    vault.index_md.write_text(
        text.replace("stale-lesson-01", "removed"), encoding="utf-8"
    )
    out = doctor(vault)
    assert "index: STALE" in out
    assert "agentbrain index" in out
    assert "1 issue(s) found" in out
