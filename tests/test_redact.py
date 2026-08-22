"""Tests for secret redaction on ingest and lint (v0.4.1)."""
from __future__ import annotations

from agentbrain.api import memory_ingest, memory_lint
from agentbrain.redact import redaction_hint, scan
from agentbrain.vault import Vault


def test_scan_detects_common_credentials():
    text = (
        "the key is sk-abc123def456ghi789jkl and aws AKIAIOSFODNN7EXAMPLE "
        "plus ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 here"
    )
    kinds = {k for k, _ in scan(text)}
    assert "OpenAI-style key (sk-…)" in kinds
    assert "AWS access key id (AKIA…)" in kinds
    assert "GitHub token (ghp_/gho_/ghu_…)" in kinds


def test_scan_detects_assignments_and_headers():
    for text in (
        "password: hunter2secretvalue",
        "api_key = aVeryLongSecretValue1",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    ):
        assert scan(text), f"missed: {text}"


def test_scan_detects_private_key_block():
    assert scan("-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n")


def test_placeholders_are_exempt():
    safe = [
        "use ${ENV:DEEPSEEK_API_KEY} for auth",
        "run with ${env:openai_key} set",
        "put your sk-xxxxx here",
        "set YOUR_API_KEY before deploy",
        "the placeholder <api-key> goes in .env",
        "password: changeme",
    ]
    for text in safe:
        assert scan(text) == [], f"false positive: {text}"


def test_ordinary_prose_never_flags():
    texts = [
        "The migrations must run before deploy on Sundays at 21:00.",
        "TRAE 启动 MCP 时含空格路径会被截断，用 junction 规避。",
        "BM25 with CJK bigrams works out of the box (lesson 0x12 3456).",
        "The proxy listens on 127.0.0.1:7897 via Clash Verge.",
    ]
    for text in texts:
        assert scan(text) == [], f"false positive: {text}"


def test_ingest_refuses_credentials(vault: Vault):
    out = memory_ingest(
        case_id="leak",
        lesson="my token is sk-ant-api03-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
        tags=["x"],
        vault=vault,
    )
    assert out.startswith("Refused:")
    assert "${ENV:VAR_NAME}" in out
    assert vault.get("leak-lesson-01") is None  # nothing was written


def test_ingest_refuses_credentials_in_summary(vault: Vault):
    out = memory_ingest(
        case_id="leak2",
        lesson="harmless lesson body text",
        source_summary="key AKIAIOSFODNN7EXAMPLE leaked",
        tags=[],
        vault=vault,
    )
    assert out.startswith("Refused:")
    assert vault.get("leak2-lesson-01") is None


def test_ingest_refuses_credentials_in_case_id(vault: Vault):
    out = memory_ingest(
        case_id="leak-ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
        lesson="harmless lesson body text",
        tags=[],
        vault=vault,
    )
    assert out.startswith("Refused:")
    assert not any(p.name.startswith("leak-ghp") for p in vault.learnings_dir.glob("*.md"))


def test_ingest_refuses_credentials_in_tags(vault: Vault):
    out = memory_ingest(
        case_id="leak3",
        lesson="harmless lesson body text",
        tags=["sk-abc123def456ghi789jkl"],
        vault=vault,
    )
    assert out.startswith("Refused:")
    assert vault.get("leak3-lesson-01") is None


def test_ingest_accepts_placeholder_lessons(vault: Vault):
    out = memory_ingest(
        case_id="safe",
        lesson="deploy needs ${ENV:DEEPSEEK_API_KEY}; never hardcode the sk-xxx value",
        tags=["deploy"],
        vault=vault,
    )
    assert out.startswith("Saved safe-lesson-01")
    assert vault.get("safe-lesson-01") is not None


def test_lint_reports_secret_in_existing_lesson(vault: Vault):
    p = vault.learnings_dir / "leaked-lesson-01.md"
    p.write_text(
        "---\ncase_id: leaked\ntags: [ops]\n---\n\nthe api_key: "
        "aVeryLongSecretValue1 was found in logs\n",
        encoding="utf-8",
    )
    out = memory_lint(vault=vault)
    assert "SECRET leaked-lesson-01" in out
    # lint must not modify the file
    assert "aVeryLongSecretValue1" in p.read_text(encoding="utf-8")


def test_redaction_hint_mentions_all_kinds():
    hint = redaction_hint([("OpenAI-style key (sk-…)", "sk-abc…")])
    assert "OpenAI-style key" in hint and "Refused" in hint
