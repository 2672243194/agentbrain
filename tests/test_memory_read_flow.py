import datetime as dt

import pytest

from agentbrain import api
from agentbrain.vault import Vault


@pytest.fixture
def local_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    return vault


def save(vault, case, content, **fields):
    lesson = vault.new_lesson(case, content, content, ["test"])
    for name, value in fields.items():
        setattr(lesson, name, value)
    vault._save_locked(lesson, rebuild=False)
    return lesson


def test_retired_read_points_to_replacement_without_reinforcing_old_content(local_vault):
    current = save(local_vault, "current", "CURRENT_INSTRUCTIONS")
    retired = save(local_vault, "old", "OLD_INSTRUCTIONS", superseded_by=current.lesson_id)
    out = api.memory_read([retired.lesson_id], vault=local_vault)
    assert "Superseded" in out
    assert current.lesson_id in out
    assert "OLD_INSTRUCTIONS" not in out
    assert local_vault.get(retired.lesson_id).use_count == 0


def test_expired_read_is_labelled_and_not_reinforced(local_vault):
    expired = save(local_vault, "expired", "historical instructions", valid_until=dt.date.today().isoformat())
    out = api.memory_read([expired.lesson_id], vault=local_vault)
    assert "EXPIRED" in out
    assert "historical instructions" in out
    assert local_vault.get(expired.lesson_id).use_count == 0


def test_full_query_and_read_do_not_repeat_the_body_as_gist_or_summary(local_vault):
    lesson = save(local_vault, "short", "UNIQUE_BODY_MARKER")
    assert api.memory_query("UNIQUE_BODY_MARKER", mode="full", vault=local_vault).count("UNIQUE_BODY_MARKER") == 1
    assert api.memory_read([lesson.lesson_id], vault=local_vault).count("UNIQUE_BODY_MARKER") == 1


def test_read_limit_reports_rejection_without_partial_counting(local_vault):
    lessons = [save(local_vault, f"case-{i}", f"body {i}") for i in range(11)]
    out = api.memory_read([lesson.lesson_id for lesson in lessons], vault=local_vault)
    assert "Refused" in out and "10" in out
    assert all(local_vault.get(lesson.lesson_id).use_count == 0 for lesson in lessons)


def test_read_normalizes_handwritten_summary(local_vault):
    lesson = save(local_vault, "summary", "body", source_summary="first line\n## injected heading")
    out = api.memory_read([lesson.lesson_id], vault=local_vault)
    assert "\n## injected heading" not in out
    assert "first line ## injected heading" in out


def test_index_excerpt_shows_query_match_beyond_long_introduction(local_vault):
    save(local_vault, "ports", "General setup notes. " * 30 + "EADDRINUSE: inspect port ownership before restarting.", source_summary="Service startup troubleshooting")
    out = api.memory_query("EADDRINUSE", vault=local_vault)
    gist = next(line for line in out.splitlines() if "gist:" in line)
    assert "EADDRINUSE" in gist
    assert len(gist.removeprefix("   gist: ")) <= 160


def test_index_query_guides_selective_full_reads(local_vault):
    save(local_vault, "guide", "retrieval guidance")
    out = api.memory_query("retrieval", vault=local_vault)
    assert "memory_read" in out
    assert "not read this session" in out
    assert local_vault.get("guide-lesson-01").use_count == 0


def test_read_preserves_indented_markdown_code(local_vault):
    lesson = save(local_vault, "indented", "placeholder")
    lesson.path.write_text("---\ncase_id: indented\n---\n\n    print('code block')\n", encoding="utf-8")
    out = api.memory_read([lesson.lesson_id], vault=local_vault)
    assert "\n    print('code block')" in out


def test_gist_selects_complete_matching_sentence(local_vault):
    action = "EADDRINUSE: inspect port ownership before restarting."
    save(local_vault, "sentence", "General setup. " * 40 + action, source_summary="Startup notes")
    out = api.memory_query("EADDRINUSE", vault=local_vault)
    assert next(line for line in out.splitlines() if "gist:" in line) == "   gist: " + action


def test_gist_finds_match_inside_long_sentence_and_single_cjk(local_vault):
    save(local_vault, "long", "背景描述" * 100 + "图片需要压缩", source_summary="处理步骤")
    out = api.memory_query("图", vault=local_vault)
    assert "图片需要压缩" in next(line for line in out.splitlines() if "gist:" in line)


def test_old_read_warns_without_changing_verification_date(local_vault):
    earlier = (dt.date.today() - dt.timedelta(days=100)).isoformat()
    lesson = save(local_vault, "stale", "recheck local assumptions", last_verified_at=earlier)
    assert "STALE" in api.memory_read([lesson.lesson_id], vault=local_vault)
    assert local_vault.get(lesson.lesson_id).last_verified_at == earlier


@pytest.mark.parametrize("field", ["title", "change"])
def test_profile_suggestions_refuse_credential_shaped_input(local_vault, field):
    arguments = {"title": "Runtime settings", "change": "Use environment variables."}
    arguments[field] = "password: syntheticCredentialValue42"
    before = list(local_vault.root.rglob("*"))
    out = api.memory_suggest(**arguments, vault=local_vault)
    assert out.startswith("Refused:")
    assert "${ENV:VAR_NAME}" in out
    assert list(local_vault.root.rglob("*")) == before


def test_profile_suggestions_allow_environment_placeholders(local_vault):
    out = api.memory_suggest("Credentials", "Use ${ENV:API_KEY} at runtime.", vault=local_vault)
    assert "Suggestion saved" in out
    assert len(list((local_vault.root / "Agent-Profile" / "_suggestions").glob("*.md"))) == 1
