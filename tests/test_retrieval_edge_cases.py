"""Public ingest IDs must remain safe and readable on every platform."""

import pytest

from agentbrain import api
from agentbrain.vault import Vault


@pytest.fixture
def local_vault(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    monkeypatch.setattr(vault, "_snapshot_locked", lambda message: None)
    return vault


@pytest.mark.parametrize(
    "case_id",
    [
        "my..case", "...", "prefix...suffix", "name\x00case", "name\x01case",
        "name\x7fcase", "CON.notes", "aux.log", "COM1.cache", "LPT9.data",
        "COM\u00b9.cache", "case/with\\separators", "a" * 100 + "..tail",
    ],
)
def test_ingest_normalizes_case_ids_to_readable_lessons(local_vault, case_id):
    result = api.memory_ingest(case_id, "Reusable boundary guidance", vault=local_vault)
    assert result.startswith("Saved ")
    lessons = local_vault.lessons()
    assert len(lessons) == 1
    lesson = lessons[0]
    assert len(lesson.case_id) <= api._CASE_ID_MAX
    assert ".." not in lesson.lesson_id
    assert local_vault.get(lesson.lesson_id) is not None
    assert "Reusable boundary guidance" in api.memory_read(lesson.lesson_id, vault=local_vault)
    assert local_vault.get(lesson.lesson_id).use_count == 1


def test_normalized_case_id_collisions_allocate_new_ids(local_vault):
    api.memory_ingest("my..case", "First boundary guidance", vault=local_vault)
    api.memory_ingest("my-case", "Second boundary guidance", vault=local_vault)
    lessons = local_vault.lessons()
    assert [lesson.lesson_id for lesson in lessons] == ["my-case-lesson-01", "my-case-lesson-02"]
    assert "First boundary guidance" in api.memory_read(lessons[0].lesson_id, vault=local_vault)
    assert "Second boundary guidance" in api.memory_read(lessons[1].lesson_id, vault=local_vault)


def test_safe_case_ids_keep_existing_names(local_vault):
    for case_id in ["normal", "module.v1", "CON", "case_1"]:
        api.memory_ingest(case_id, "Keep a stable case identifier", vault=local_vault)
        assert local_vault.get(f"{case_id}-lesson-01") is not None


def test_case_variants_never_overwrite_existing_lessons(local_vault):
    api.memory_ingest("Alpha", "FIRST distinct advice", vault=local_vault)
    api.memory_ingest("alpha", "SECOND distinct advice", vault=local_vault)
    lessons = local_vault.lessons()
    assert len(lessons) == 2
    assert {lesson.content for lesson in lessons} == {"FIRST distinct advice", "SECOND distinct advice"}
