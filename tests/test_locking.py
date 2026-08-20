"""Tests for concurrency safety, atomic writes, and robustness fixes."""
from __future__ import annotations

import threading

import pytest

from agentbrain.api import memory_ingest, memory_query, memory_suggest
from agentbrain.vault import Vault
from agentbrain.locking import VaultLockTimeout, vault_lock


def test_lock_is_reentrant_same_thread(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    with vault_lock(root):
        with vault_lock(root):
            pass  # nested acquisition must not deadlock
    assert not (root / "Case-Learnings" / ".vault.lock").exists()


def test_lock_serializes_threads(tmp_path):
    root = tmp_path / "vault"
    (root / "Case-Learnings").mkdir(parents=True)
    order: list[str] = []

    def worker(name: str) -> None:
        with vault_lock(root):
            order.append(f"{name}:in")
            import time

            time.sleep(0.05)
            order.append(f"{name}:out")

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # every ":in" must be immediately followed by its own ":out"
    pairs = list(zip(order[0::2], order[1::2]))
    assert len(pairs) == 4
    assert all(i.endswith(":in") and o == i.replace(":in", ":out") for i, o in pairs)


def test_lock_timeout_and_stale_reclaim(tmp_path):
    import os

    root = tmp_path / "vault"
    (root / "Case-Learnings").mkdir(parents=True)
    lock = root / "Case-Learnings" / ".vault.lock"

    # fresh foreign lock (another process holds it) → acquisition times out
    lock.write_text("999999", encoding="utf-8")
    with pytest.raises(VaultLockTimeout):
        with vault_lock(root, timeout=0.1):
            pass

    # old foreign lock (holder crashed) → reclaimed as stale
    os.utime(lock, (0, 0))
    with vault_lock(root, timeout=0.1):
        pass
    assert not lock.exists()


def test_concurrent_ingest_no_lost_lessons(vault: Vault):
    """Multi-agent scenario: parallel ingests must all land and not corrupt index."""
    results: list[str] = []

    def ingest_one(i: int) -> None:
        results.append(
            memory_ingest(
                case_id=f"case-{i}",
                lesson=f"lesson number {i} about topic-{i}",
                tags=[f"tag-{i}"],
                vault=vault,
            )
        )

    threads = [threading.Thread(target=ingest_one, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len([r for r in results if r.startswith("Saved")]) == 6
    lessons = vault.lessons()
    assert len(lessons) == 7  # 6 new + 1 demo lesson
    index = vault.index_md.read_text(encoding="utf-8")
    for i in range(6):
        assert f"case-{i}-lesson-01" in index


def test_bump_use_single_rebuild(vault: Vault, monkeypatch):
    calls = {"n": 0}
    real = Vault._rebuild_index_locked

    def counting(self, lessons=None):
        calls["n"] += 1
        real(self, lessons)

    monkeypatch.setattr(Vault, "_rebuild_index_locked", counting)
    for i in range(3):
        memory_ingest(
            case_id=f"c{i}", lesson=f"lesson {i}", tags=["t"], vault=vault
        )

    memory_query("lesson", top_k=3, vault=vault)  # hits 3 → must rebuild once
    assert calls["n"] >= 1
    after_query = calls["n"]
    memory_query("lesson", top_k=3, vault=vault)
    assert calls["n"] - after_query == 1  # exactly one rebuild per query


def test_stray_md_files_skipped(vault: Vault):
    (vault.learnings_dir / "README.md").write_text(
        "# notes\n\nSome human note, not a lesson.\n", encoding="utf-8"
    )
    (vault.learnings_dir / "broken.md").write_text(
        "---\n::: not yaml at all [\n---\nbody\n", encoding="utf-8"
    )
    ids = [l.lesson_id for l in vault.lessons()]
    assert "README" not in ids
    assert "broken" not in ids
    vault.rebuild_index()
    assert "README" not in vault.index_md.read_text(encoding="utf-8")


def test_query_mode_invalid_falls_back(vault: Vault):
    memory_ingest(case_id="c", lesson="content about anything", tags=[], vault=vault)
    out = memory_query("anything", mode="bogus", vault=vault)
    assert "mode=index" in out


def test_confidence_clamped(vault: Vault):
    out = memory_ingest(
        case_id="c", lesson="l", tags=[], confidence=5.0, vault=vault
    )
    assert "confidence 1.0" in out
    lesson = vault.get("c-lesson-01")
    assert lesson.confidence == 1.0


def test_suggest_same_second_no_overwrite(vault: Vault):
    memory_suggest("same title", "change one", vault=vault)
    memory_suggest("same title", "change two", vault=vault)
    files = [
        f
        for f in (vault.root / "Agent-Profile" / "_suggestions").glob("*.md")
        if f.name.lower() != "readme.md"
    ]
    assert len(files) == 2
    texts = " ".join(f.read_text(encoding="utf-8") for f in files)
    assert "change one" in texts and "change two" in texts


def test_lock_file_not_treated_as_lesson(vault: Vault):
    # the lock file lives under Case-Learnings/, not Learnings/ — verify
    lock = vault.root / "Case-Learnings" / ".vault.lock"
    with vault.locked():
        assert lock.exists()
    assert not lock.exists()
