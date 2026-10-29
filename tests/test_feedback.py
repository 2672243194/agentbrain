"""Outcome feedback must not turn reads or retries into positive evidence."""

import os
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from agentbrain import api
from agentbrain.vault import Vault


OUTCOMES = ("helpful", "partial", "ineffective", "not_applicable", "unverified")


@pytest.fixture
def local_vault(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    vault.index_md.write_text("# Handwritten index\n", encoding="utf-8")
    vault.log_md.write_text("# Existing log\n", encoding="utf-8")
    rules = vault.root / "Agent-Profile" / "Immutable" / "rules.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("# Owner-only rules\n", encoding="utf-8")
    monkeypatch.setattr(vault, "_snapshot_locked", lambda message: None)
    return vault


def write_lesson(vault, lesson_id="example", body="Check the migration before restarting."):
    path = vault.learnings_dir / f"{lesson_id}.md"
    path.write_text(
        "---\ncase_id: migration\nsource_summary: Migration checks\n"
        "tags: [database]\nuse_count: 0\nlast_verified_at: '2000-01-01'\n"
        "confidence: 0.8\nverified: true\n---\n" + body + "\n",
        encoding="utf-8",
    )
    return path


def entry(vault, lesson_id="example", outcome="helpful", **updates):
    result = {
        "lesson_id": lesson_id,
        "lesson_version": vault.get(lesson_id).version,
        "outcome": outcome,
        "environment": "Windows / Python 3.10 / local test database",
        "evidence": "The migration check identified the missing table; the repair test passed.",
    }
    result.update(updates)
    return result


def files(vault):
    return sorted((vault.case_dir / "_feedback").glob("*.md"))


def state(root):
    # The persistent OS lock is coordination state, not a feedback write.
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file() and path.name != ".vault.lock"
    }


def assert_refused_without_changes(vault, task_id, entries):
    before = state(vault.root)
    output = api.memory_feedback(task_id=task_id, entries=entries, vault=vault)
    assert output.startswith("Refused:"), output
    assert state(vault.root) == before
    return output


def test_batch_records_distinct_outcomes_without_changing_lessons_or_ranking(local_vault, monkeypatch):
    for outcome in OUTCOMES:
        write_lesson(local_vault, outcome)
    entries = [entry(local_vault, outcome, outcome) for outcome in OUTCOMES]
    before = state(local_vault.root)
    ranking = api.memory_query("migration", vault=local_vault)

    def forbidden_snapshot(*args, **kwargs):
        pytest.fail("feedback must not create a snapshot")

    monkeypatch.setattr(local_vault, "_snapshot_locked", forbidden_snapshot)
    output = api.memory_feedback("task-migration-01", entries, vault=local_vault)
    assert isinstance(output, str) and not output.startswith("Refused:"), output
    saved = files(local_vault)
    assert len(saved) == 1  # One atomic Markdown document for the whole batch.
    text = saved[0].read_text(encoding="utf-8")
    assert "task-migration-01" in text
    for item in entries:
        assert item["lesson_id"] in text
        assert item["lesson_version"] in text
        assert item["outcome"] in text
        assert item["environment"] in text
        assert item["evidence"] in text
        lesson = local_vault.get(item["lesson_id"])
        assert lesson.use_count == 0
        assert lesson.confidence == 0.8
        assert lesson.last_verified_at == "2000-01-01"
    after = state(local_vault.root)
    assert {name: after[name] for name in before} == before
    assert set(after) - set(before) == {saved[0].relative_to(local_vault.root).as_posix()}
    assert api.memory_query("migration", vault=local_vault) == ranking
    assert not (local_vault.root / ".git").exists()
    stats = api.memory_stats(vault=local_vault)
    for outcome in OUTCOMES:
        assert re.search(rf"\b{outcome}\s*:\s*1\b", stats), stats
    assert "total recorded reads: 0" in stats


def test_retry_reordering_and_duplicate_entries_do_not_add_votes(local_vault):
    write_lesson(local_vault, "first")
    write_lesson(local_vault, "second")
    first, second = entry(local_vault, "first"), entry(local_vault, "second")
    assert not api.memory_feedback("task-01", [first, second], vault=local_vault).startswith("Refused:")
    before = state(local_vault.root)
    retry = api.memory_feedback("task-01", [second, first, first], vault=local_vault)
    assert not retry.startswith("Refused:"), retry
    assert state(local_vault.root) == before
    assert len(files(local_vault)) == 1
    assert not api.memory_feedback("task-02", [first], vault=local_vault).startswith("Refused:")
    assert len(files(local_vault)) == 2


def test_conflict_rejects_entire_batch_before_writing_another_entry(local_vault):
    write_lesson(local_vault, "existing")
    write_lesson(local_vault, "new")
    prior = entry(local_vault, "existing")
    api.memory_feedback("task-01", [prior], vault=local_vault)
    assert_refused_without_changes(
        local_vault, "task-01", [entry(local_vault, "new"), dict(prior, outcome="ineffective")],
    )
    assert len(files(local_vault)) == 1


def test_conflicting_duplicate_within_first_batch_is_atomic(local_vault):
    write_lesson(local_vault)
    item = entry(local_vault)
    assert_refused_without_changes(local_vault, "task-01", [item, dict(item, outcome="partial")])
    assert not (local_vault.case_dir / "_feedback").exists()


def test_concurrent_retries_across_vault_instances_store_once(local_vault):
    write_lesson(local_vault)
    item = entry(local_vault)

    def submit(_):
        return api.memory_feedback("concurrent-task", [item], vault=Vault.open(root=local_vault.root))

    with ThreadPoolExecutor(max_workers=6) as pool:
        outputs = list(pool.map(submit, range(12)))
    assert all(not output.startswith("Refused:") for output in outputs), outputs
    assert len(files(local_vault)) == 1
    assert re.search(r"\bhelpful\s*:\s*1\b", api.memory_stats(vault=local_vault))
    assert local_vault.get("example").use_count == 0


def test_versions_track_content_but_not_read_counts_or_verification_dates(local_vault):
    path = write_lesson(local_vault)
    original = local_vault.get("example").version
    assert re.fullmatch(r"[0-9a-f]{64}", original)
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert local_vault.get("example").version == original
    read = api.memory_read(["example"], vault=local_vault)
    assert f"version: {original}" in read
    full = api.memory_query("migration", mode="full", vault=local_vault)
    assert f"version: {original}" in full
    assert local_vault.get("example").use_count == 2
    assert local_vault.get("example").version == original
    local_vault.verify(["example"])
    assert local_vault.get("example").version == original
    old = entry(local_vault)
    assert not api.memory_feedback("task-01", [old], vault=local_vault).startswith("Refused:")
    path.write_text(path.read_text(encoding="utf-8") + "Check database permissions too.\n", encoding="utf-8")
    current = local_vault.get("example").version
    assert current != original
    # A lost acknowledgement must not turn an already stored old report into
    # an error just because somebody subsequently revised the source lesson.
    before_retry = state(local_vault.root)
    assert not api.memory_feedback("task-01", [old], vault=local_vault).startswith("Refused:")
    assert state(local_vault.root) == before_retry
    assert_refused_without_changes(local_vault, "new-task", [old])
    assert not api.memory_feedback("task-01", [entry(local_vault)], vault=local_vault).startswith("Refused:")
    assert len(files(local_vault)) == 2


def test_custom_applicability_metadata_changes_the_content_version(local_vault):
    path = write_lesson(local_vault)
    original = entry(local_vault)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("case_id: migration", "case_id: migration\napplies_to: PostgreSQL 16"), encoding="utf-8")
    assert local_vault.get("example").version != original["lesson_version"]
    assert_refused_without_changes(local_vault, "task-01", [original])


def test_damaged_existing_report_blocks_duplicate_votes_and_is_visible_in_stats(local_vault):
    write_lesson(local_vault)
    item = entry(local_vault)
    api.memory_feedback("task-01", [item], vault=local_vault)
    report = files(local_vault)[0]
    report.write_text("---\nentries: [broken yaml\n---\n", encoding="utf-8")
    assert_refused_without_changes(local_vault, "task-01", [item])
    before = state(local_vault.root)
    stats = api.memory_stats(vault=local_vault)
    assert re.search(r"\bhelpful\s*:\s*0\b", stats), stats
    assert re.search(r"unreadable feedback files:\s*1\b", stats), stats
    assert state(local_vault.root) == before


def test_interrupted_atomic_replace_leaves_no_partial_batch_and_retry_can_succeed(local_vault, monkeypatch):
    from agentbrain import locking

    write_lesson(local_vault, "first")
    write_lesson(local_vault, "second")
    entries = [entry(local_vault, "first"), entry(local_vault, "second")]
    before = state(local_vault.root)
    attempts = []

    def unavailable_destination(source, destination):
        attempts.append((source, destination))
        assert source.exists()  # Exercise the real staged-write cleanup path.
        raise OSError("Synthetic atomic replace failure")

    with monkeypatch.context() as patch:
        patch.setattr(locking.os, "replace", unavailable_destination)
        try:
            output = api.memory_feedback("task-01", entries, vault=local_vault)
        except OSError:
            pass
        else:
            assert output.startswith("Refused:"), output
    assert len(attempts) == 1
    assert state(local_vault.root) == before
    assert not files(local_vault)
    assert not list((local_vault.case_dir / "_feedback").glob("*.tmp"))
    assert not api.memory_feedback("task-01", entries, vault=local_vault).startswith("Refused:")
    assert len(files(local_vault)) == 1
    assert re.search(r"\bhelpful\s*:\s*2\b", api.memory_stats(vault=local_vault))


@pytest.mark.parametrize("field", ["task_id", "lesson_id", "lesson_version", "outcome", "environment", "evidence"])
def test_secret_shaped_values_are_refused_without_echoing_them(local_vault, field):
    write_lesson(local_vault)
    item = entry(local_vault)
    credential = "SyntheticFeedbackCredential12345"
    value = "password: " + credential
    task = "task-01"
    if field == "task_id":
        task = value
    else:
        item[field] = value
    output = assert_refused_without_changes(local_vault, task, [item])
    assert credential not in output
    assert not files(local_vault)


@pytest.mark.parametrize("field", ["lesson_id", "lesson_version", "outcome", "environment", "evidence"])
@pytest.mark.parametrize("value", [None, 1, "", "x" * 10000])
def test_invalid_or_oversized_entry_fields_have_no_side_effects(local_vault, field, value):
    write_lesson(local_vault)
    item = entry(local_vault)
    item[field] = value
    assert_refused_without_changes(local_vault, "task-01", [item])


@pytest.mark.parametrize("task_id", [None, 1, "", " ", "x" * 10000])
def test_invalid_task_identity_has_no_side_effects(local_vault, task_id):
    write_lesson(local_vault)
    assert_refused_without_changes(local_vault, task_id, [entry(local_vault)])


@pytest.mark.parametrize("entries", [None, {}, "example", [], [None], [{}]])
def test_invalid_batch_shape_is_refused(local_vault, entries):
    assert_refused_without_changes(local_vault, "task-01", entries)


def test_oversized_batch_and_unknown_fields_are_refused(local_vault):
    write_lesson(local_vault)
    assert_refused_without_changes(local_vault, "task-01", [entry(local_vault)] * 11)
    assert_refused_without_changes(local_vault, "task-01", [entry(local_vault, unsupported="extra")])


@pytest.mark.parametrize("lesson_id", ["missing", "../outside", "..\\outside", "C:\\outside", "CON"])
def test_missing_or_unsafe_lesson_rejects_whole_batch(local_vault, lesson_id):
    write_lesson(local_vault)
    item = entry(local_vault)
    assert_refused_without_changes(local_vault, "task-01", [item, dict(item, lesson_id=lesson_id)])
    assert not files(local_vault)


@pytest.mark.skipif(os.name != "nt", reason="Windows filename aliases")
def test_windows_case_aliases_do_not_create_duplicate_feedback(local_vault):
    write_lesson(local_vault, "Case-lesson-01")
    original = entry(local_vault, "Case-lesson-01")
    assert not api.memory_feedback("task-01", [original], vault=local_vault).startswith("Refused:")
    before = state(local_vault.root)
    alias = dict(original, lesson_id="CASE-LESSON-01")
    assert not api.memory_feedback("task-01", [alias], vault=local_vault).startswith("Refused:")
    assert state(local_vault.root) == before


def test_uninitialized_vault_is_not_created(tmp_path, monkeypatch):
    root = tmp_path / "missing"
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(root))
    output = api.memory_feedback("task-01", [{
        "lesson_id": "example", "lesson_version": "0" * 64, "outcome": "helpful",
        "environment": "Test environment", "evidence": "The check passed.",
    }])
    assert "vault not found" in output
    assert not root.exists()
