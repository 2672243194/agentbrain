"""Robustness, token-efficiency and convenience tests for the v0.4.6 batch."""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

from agentbrain.api import memory_ingest, memory_lint, memory_query
from agentbrain.locking import vault_lock
from agentbrain.redact import scan
from agentbrain.snapshot import Snapshot
from agentbrain.vault import Vault


def test_ingest_onelines_multiline_summary(vault: Vault):
    memory_ingest(
        case_id="ml",
        lesson="body",
        source_summary="line one\nline two\nline three",
        tags=["t"],
        vault=vault,
    )
    lesson = vault.get("ml-lesson-01")
    assert "\n" not in lesson.source_summary
    row = [
        ln
        for ln in vault.index_md.read_text(encoding="utf-8").splitlines()
        if "ml-lesson-01" in ln
    ][0]
    assert "line one line two line three" in row


def test_ingest_caps_summary_length(vault: Vault):
    memory_ingest(case_id="cap", lesson="body", source_summary="x" * 300, vault=vault)
    assert len(vault.get("cap-lesson-01").source_summary) <= 60


def test_index_onelines_hand_edited_summary(vault: Vault):
    p = vault.learnings_dir / "hand-sum-lesson-01.md"
    p.write_text(
        "---\ncase_id: hand-sum\nsource_summary: |\n  first line\n  second line\n"
        "tags: [t]\n---\n\nbody\n",
        encoding="utf-8",
    )
    vault.rebuild_index()
    row = [
        ln
        for ln in vault.index_md.read_text(encoding="utf-8").splitlines()
        if "hand-sum-lesson-01" in ln
    ][0]
    assert "first line second line" in row


def test_query_output_is_compact(vault: Vault):
    memory_ingest(case_id="fmt", lesson="compact output check", tags=["alpha"], vault=vault)
    lines = memory_query("compact", vault=vault).splitlines()
    i = next(idx for idx, ln in enumerate(lines) if ln.startswith("1. [fmt-lesson-01]"))
    assert "tags: alpha · path: " in lines[i + 1]
    assert lines[i + 2].startswith("   gist: ")
    assert len(lines) == i + 3  # compact layout: rank + tags/path + gist, nothing after


def test_query_top_k_clamped_high_and_low(vault: Vault):
    for i in range(25):
        p = vault.learnings_dir / f"tk{i:02d}-lesson-01.md"
        p.write_text(
            f"---\ncase_id: tk{i:02d}\nsource_summary: clamp fill lesson {i}\n"
            "tags: []\n---\n\nclamp fill shared keyword\n",
            encoding="utf-8",
        )
    out = memory_query("clamp fill", top_k=100, vault=vault)
    assert out.splitlines()[0].startswith("20 lesson(s) matched")
    out = memory_query("clamp fill", top_k=0, vault=vault)
    assert out.splitlines()[0].startswith("1 lesson(s) matched")


def test_query_tag_filter(vault: Vault):
    memory_ingest(case_id="ta", lesson="deploy notes", tags=["deploy"], vault=vault)
    memory_ingest(case_id="tb", lesson="deploy notes too", tags=["misc"], vault=vault)
    out = memory_query("deploy", tag="deploy", vault=vault)
    assert "ta-lesson-01" in out
    assert "tb-lesson-01" not in out
    out = memory_query("deploy", tag="#deploy", vault=vault)  # leading # tolerated
    assert "ta-lesson-01" in out


def test_query_tag_filter_no_match_message(vault: Vault):
    memory_ingest(case_id="tc", lesson="deploy notes", tags=["deploy"], vault=vault)
    out = memory_query("deploy", tag="nosuch", vault=vault)
    assert "No lessons tagged 'nosuch'" in out


def test_query_empty_is_refused(vault: Vault):
    out = memory_query("   ", vault=vault)
    assert "empty query" in out
    assert "broader keywords" not in out


def test_ingest_reports_dropped_tags(vault: Vault):
    out = memory_ingest(case_id="tg", lesson="body", tags=list("abcdefghij"), vault=vault)
    assert "tags capped at 8" in out
    assert "dropped: i, j" in out
    assert vault.get("tg-lesson-01").tags == list("abcdefgh")


def test_lint_rejects_unknown_scope(vault: Vault):
    assert "Invalid scope" in memory_lint(scope="bogus", vault=vault)


def test_lint_skips_superseded_for_orphan_lowconf_expired(vault: Vault):
    keeper = vault.new_lesson("k", "keeper summary", "keeper content", ["t"])
    vault.save(keeper, action="ingest")
    retired = vault.new_lesson("r", "retired summary", "retired content", [])
    retired.superseded_by = keeper.lesson_id
    retired.confidence = 0.2
    retired.valid_until = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    vault.save(retired)
    out = memory_lint(vault=vault)
    assert "ORPHAN" not in out
    assert "LOWCONF" not in out
    assert "EXPIRED" not in out


def test_lint_still_reports_dangling_on_superseded(vault: Vault):
    ghost = vault.new_lesson("r2", "ghost summary", "ghost content", ["t"])
    ghost.superseded_by = "no-such-lesson-99"
    vault.save(ghost)
    out = memory_lint(vault=vault)
    assert "DANGLING r2-lesson-01" in out
    assert "remedy: fix superseded_by by hand" in out


def test_scan_allows_lesson_id_shaped_words():
    assert scan("see pypi-publish-workflow-lesson-01 for details") == []


def test_scan_still_flags_real_pypi_token():
    hits = scan("pypi-AgEIcHlwaS10b2tlblJlYWxWYWxpZEtleTEyMw")
    assert hits and hits[0][0].startswith("PyPI")


def test_snapshot_commit_three_states(vault: Vault):
    snap = Snapshot(vault.root)
    (vault.learnings_dir / "three-state-lesson-01.md").write_text(
        "---\ncase_id: ts\ntags: [t]\n---\n\nbody\n", encoding="utf-8"
    )
    with vault.locked():
        assert snap.commit("msg") == "committed"
        assert snap.commit("msg") == "clean"


def test_snapshot_commit_failed_when_disabled(tmp_path):
    assert Snapshot(tmp_path / "no-git").commit("x").startswith("failed")


def test_index_has_no_used_column_and_bump_leaves_it_untouched(vault: Vault):
    memory_ingest(case_id="iu", lesson="index used column check", tags=["t"], vault=vault)
    before = vault.index_md.read_text(encoding="utf-8")
    assert "| lesson | summary | tags | case | verified |" in before
    vault.bump_use(["iu-lesson-01"])
    assert vault.index_md.read_text(encoding="utf-8") == before
    assert vault.get("iu-lesson-01").use_count == 1


def test_cli_piped_output_survives_non_utf8_locale(tmp_path):
    from agentbrain import scaffold

    root = tmp_path / "vault"
    scaffold.init(root)
    v = Vault.open(root=root)
    memory_ingest(case_id="enc", lesson="note 🚨 emoji", vault=v)
    env = dict(os.environ, AGENTBRAIN_VAULT=str(root), PYTHONIOENCODING="cp936")
    r = subprocess.run(
        [sys.executable, "-m", "agentbrain", "query", "emoji"],
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "🚨" in r.stdout


def test_nested_locks_across_vaults_do_not_deadlock(tmp_path):
    from agentbrain import scaffold

    va, vb = tmp_path / "va", tmp_path / "vb"
    scaffold.init(va)
    scaffold.init(vb)
    with vault_lock(va, timeout=2.0):
        with vault_lock(vb, timeout=2.0):
            with vault_lock(va, timeout=2.0):  # re-enter the outer vault lock
                pass
