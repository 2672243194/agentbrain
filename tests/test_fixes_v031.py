"""Regression tests for round-2 bug fixes (v0.3.1)."""
from __future__ import annotations

import threading

from agentbrain.api import memory_ingest, memory_lint, memory_query
from agentbrain.vault import Vault


def test_concurrent_same_case_ingest_no_overwrite(vault: Vault):
    """Parallel ingests sharing one case_id must get distinct lesson_ids."""
    barrier = threading.Barrier(4)

    def ingest(i: int) -> None:
        barrier.wait()  # maximize the race window on id allocation
        memory_ingest(
            case_id="race",
            lesson=f"lesson {i} about the same case topic",
            tags=["race"],
            vault=vault,
        )

    threads = [threading.Thread(target=ingest, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ids = sorted(l.lesson_id for l in vault.lessons() if l.case_id == "race")
    assert len(ids) == 4, f"expected 4 distinct ids, got {ids}"
    assert len(set(ids)) == 4


def test_confidence_zero_roundtrip(vault: Vault):
    memory_ingest(
        case_id="c0", lesson="zero confidence lesson", tags=[], confidence=0.0, vault=vault
    )
    lesson = vault.get("c0-lesson-01")
    assert lesson.confidence == 0.0  # must not silently become 0.8


def test_lint_proposals_same_second_distinct(vault: Vault):
    for i in range(2):
        memory_ingest(
            case_id=f"dup{i}",
            lesson="identical lesson text about identical things",
            tags=["t"],
            vault=vault,
        )
    # force the two lessons to look like duplicates: same summary via re-save
    a = vault.get("dup0-lesson-01")
    b = vault.get("dup1-lesson-01")
    a.source_summary, b.source_summary = "same summary here", "same summary here"
    a.tags = b.tags = ["dup"]
    vault.save(a)
    vault.save(b)

    r1 = memory_lint(vault=vault)
    r2 = memory_lint(vault=vault)
    assert "DUPLICATE" in r1 and "DUPLICATE" in r2
    p1 = r1.split("Proposal written: ")[1].splitlines()[0]
    p2 = r2.split("Proposal written: ")[1].splitlines()[0]
    assert p1 != p2  # same-second runs never share a file


def test_lint_merge_direction_follows_use_count(vault: Vault):
    memory_ingest(case_id="d1", lesson="alpha text", tags=["dup"], vault=vault)
    memory_ingest(case_id="d2", lesson="beta text", tags=["dup"], vault=vault)
    a, b = vault.get("d1-lesson-01"), vault.get("d2-lesson-01")
    a.source_summary, b.source_summary = "same summary here", "same summary here"
    a.use_count, b.use_count = 7, 1  # a is clearly the more-used lesson
    vault.save(a)
    vault.save(b)

    out = memory_lint(vault=vault)
    assert "DUPLICATE" in out
    proposal = vault.root / out.split("Proposal written: ")[1].splitlines()[0]
    text = proposal.read_text(encoding="utf-8")
    assert "supersede: d2-lesson-01 -> d1-lesson-01" in text  # gone -> keeper
    assert "supersede: d1-lesson-01 -> d2-lesson-01" not in text


def test_query_bump_and_confidence_display(vault: Vault):
    memory_ingest(case_id="qc", lesson="quantum cache lesson", tags=["q"], vault=vault)
    out = memory_query("quantum cache", vault=vault)
    assert "qc-lesson-01" in out
    lesson = vault.get("qc-lesson-01")
    assert lesson.use_count == 1
