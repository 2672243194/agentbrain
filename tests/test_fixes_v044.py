"""Regression tests for the v0.4.4 hardening round."""
from __future__ import annotations

import datetime as dt

from agentbrain.api import memory_ingest, memory_lint
from agentbrain.redact import scan
from agentbrain.retrieval import search_lessons
from agentbrain.vault import Vault

_SHA1 = "686e4c9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"


def test_scan_allows_git_sha1():
    assert scan(f"release commit {_SHA1} tagged v1.0.0") == []
    assert scan(f"sha256 differs, but git short ids and full ids like {_SHA1} are fine") == []


def test_scan_still_flags_real_aws_secret():
    # 40 chars of base64 with non-hex characters — an actual AWS secret shape
    secret = "AbCd+/1234EfGhIjKlMnOpQrStUvWxYz09876543"
    assert len(secret) == 40
    kinds = {k for k, _ in scan(f"aws_secret = {secret}")}
    assert any("AWS secret" in k for k in kinds)


def test_scan_bearer_prose_without_digits_is_allowed():
    assert scan("Bearer authentication-tokens are sent on every request") == []


def test_scan_bearer_token_with_digits_still_flagged():
    hits = scan("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    assert any(k == "Bearer header" for k, _ in hits)


def test_lesson_saved_with_bom_is_visible(vault: Vault):
    p = vault.learnings_dir / "bom-case-lesson-01.md"
    body = (
        "---\n"
        "case_id: bom-case\n"
        "tags: [bom]\n"
        "source_summary: BOM lesson about windows editors\n"
        "use_count: 0\n"
        "---\n\n"
        "Content saved by Notepad with a UTF-8 BOM.\n"
    )
    p.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    ids = [l.lesson_id for l in vault.lessons()]
    assert "bom-case-lesson-01" in ids
    assert [l.lesson_id for l, _ in search_lessons(vault.lessons(), "BOM windows editors")]


def test_verified_string_false_parses_false(vault: Vault):
    p = vault.learnings_dir / "str-case-lesson-01.md"
    p.write_text(
        "---\ncase_id: str-case\ntags: [t]\nverified: 'false'\nsource_summary: quoted false\n---\n\nx\n",
        encoding="utf-8",
    )
    assert vault.get("str-case-lesson-01").verified is False
    p.write_text(
        "---\ncase_id: str-case\ntags: [t]\nverified: no\nsource_summary: quoted false\n---\n\nx\n",
        encoding="utf-8",
    )
    assert vault.get("str-case-lesson-01").verified is False


def test_long_case_id_is_truncated(vault: Vault):
    out = memory_ingest(case_id="c" * 300, lesson="short body", tags=["t"], vault=vault)
    assert out.startswith("Saved ")
    saved = [p for p in vault.learnings_dir.glob("*.md") if p.name.startswith("cccccc")]
    assert saved, "lesson file not found"
    assert len(saved[0].name) <= 48 + len("-lesson-01.md")
    assert vault.relpath(saved[0]) in out


def test_lint_reports_secret_in_tags(vault: Vault):
    p = vault.learnings_dir / "tagleak-case-lesson-01.md"
    p.write_text(
        "---\ncase_id: tagleak-case\ntags: [sk-abc123def456ghi789jkl]\nsource_summary: clean\nuse_count: 0\n---\n\nharmless body\n",
        encoding="utf-8",
    )
    out = memory_lint(vault=vault)
    assert "SECRET tagleak-case-lesson-01" in out


def test_verify_updates_last_verified_and_clears_stale(vault: Vault):
    old = (dt.date.today() - dt.timedelta(days=200)).isoformat()
    p = vault.learnings_dir / "stale-case-lesson-01.md"
    p.write_text(
        f"---\ncase_id: stale-case\ntags: [t]\nsource_summary: stale lesson\nlast_verified_at: {old}\nuse_count: 0\n---\n\nstill true today\n",
        encoding="utf-8",
    )
    out = memory_lint(vault=vault)
    assert "STALE stale-case-lesson-01" in out

    verified, missing = vault.verify(["stale-case-lesson-01"])
    assert verified == ["stale-case-lesson-01"]
    assert missing == []
    lesson = vault.get("stale-case-lesson-01")
    assert lesson.last_verified_at == dt.date.today().isoformat()
    index = vault.index_md.read_text(encoding="utf-8")
    assert lesson.last_verified_at in index

    out = memory_lint(vault=vault)
    assert "STALE stale-case-lesson-01" not in out


def test_verify_reports_missing_ids(vault: Vault):
    verified, missing = vault.verify(["no-such-lesson"])
    assert verified == []
    assert missing == ["no-such-lesson"]
    verified, missing = vault.verify(["case-demo-lesson-01", "no-such-lesson"])
    assert verified == ["case-demo-lesson-01"]
    assert missing == ["no-such-lesson"]


def test_ingest_warns_on_near_duplicate_summary(vault: Vault):
    first = memory_ingest(
        case_id="dup",
        lesson="first body",
        source_summary="PyPI 上传后 JSON API 有缓存延迟",
        tags=["pypi"],
        vault=vault,
    )
    assert "note:" not in first
    second = memory_ingest(
        case_id="dup2",
        lesson="second body with more words",
        source_summary="PyPI 上传后 JSON API 有缓存延迟",
        tags=["pypi"],
        vault=vault,
    )
    assert second.startswith("Saved ")
    assert "note: similar active lesson(s) exist — dup-lesson-01" in second


def test_ingest_distinct_summaries_get_no_warning(vault: Vault):
    memory_ingest(
        case_id="topic-a",
        lesson="body a",
        source_summary="Node fetch 不走 Windows 系统代理",
        tags=["proxy"],
        vault=vault,
    )
    out = memory_ingest(
        case_id="topic-b",
        lesson="body b",
        source_summary="PyPI 包名与已有项目过于相似会被拒",
        tags=["pypi"],
        vault=vault,
    )
    assert "note:" not in out
