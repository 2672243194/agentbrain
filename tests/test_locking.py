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
    with vault_lock(root):  # released → immediately re-acquirable
        pass


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


def test_lock_timeout_while_held(tmp_path):
    root = tmp_path / "vault"
    (root / "Case-Learnings").mkdir(parents=True)
    held = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with vault_lock(root):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    held.wait(timeout=5)
    with pytest.raises(VaultLockTimeout):
        with vault_lock(root, timeout=0.2):
            pass
    release.set()
    t.join()
    with vault_lock(root, timeout=5):  # after release → acquirable again
        pass


def test_leftover_lock_file_does_not_block(tmp_path):
    """A lock file left by a crashed process must not block anyone: the lock
    lives in the OS, not in the file's existence."""
    root = tmp_path / "vault"
    (root / "Case-Learnings").mkdir(parents=True)
    lock = root / "Case-Learnings" / ".vault.lock"
    lock.write_text("999999", encoding="utf-8")
    with vault_lock(root, timeout=1.0):
        pass


def test_killed_process_releases_lock_instantly(tmp_path):
    """Crash availability: after the holder is killed, the next writer must
    acquire immediately — no multi-second stale window."""
    import subprocess
    import sys

    root = tmp_path / "vault"
    (root / "Case-Learnings").mkdir(parents=True)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time\n"
            f"from agentbrain.locking import vault_lock\n"
            f"from pathlib import Path\n"
            f"with vault_lock(Path(r'{root}')):\n"
            "    print('held', flush=True)\n"
            "    time.sleep(30)\n",
        ],
        stdout=subprocess.PIPE,
    )
    try:
        holder.stdout.readline()  # wait until the child actually holds it
        with pytest.raises(VaultLockTimeout):
            with vault_lock(root, timeout=0.3):
                pass  # still held
        holder.kill()
        holder.wait(timeout=10)
        import time as _t

        t0 = _t.monotonic()
        with vault_lock(root, timeout=10.0):
            elapsed = _t.monotonic() - t0
        assert elapsed < 5.0  # released by OS at process death, not after 60 s
    finally:
        if holder.poll() is None:
            holder.kill()


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
    # the lock file lives under Case-Learnings/, not Learnings/ — verify it
    # exists while held, persists after release, and never enters the index
    lock = vault.root / "Case-Learnings" / ".vault.lock"
    with vault.locked():
        assert lock.exists()
    assert lock.name not in vault.index_md.read_text(encoding="utf-8")
    assert all(
        l.lesson_id != ".vault" for l in vault.lessons(include_superseded=True)
    )
