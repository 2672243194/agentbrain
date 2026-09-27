"""Read identity and trustworthy Markdown log regressions."""

import datetime as dt
import os

import pytest

from agentbrain import api
from agentbrain.vault import Vault


@pytest.fixture
def local_vault(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    monkeypatch.setattr(vault, "_snapshot_locked", lambda message: None)
    return vault


def write_lesson(vault, lesson_id, content="Useful guidance", count=0):
    path = vault.learnings_dir / f"{lesson_id}.md"
    path.write_text(
        f"---\ncase_id: guidance\nuse_count: {count}\n---\n{content}\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.skipif(os.name != "nt", reason="Windows filename case semantics")
def test_windows_read_aliases_return_and_count_one_lesson(local_vault):
    write_lesson(local_vault, "Case-lesson-01")
    output, status = api._memory_read_result(
        ["Case-lesson-01", "CASE-LESSON-01", "case-lesson-01"], local_vault,
    )
    assert status == 0
    assert output.count("Useful guidance") == 1
    assert "Not found" not in output
    assert local_vault.get("Case-lesson-01").use_count == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows filename case semantics")
def test_windows_vault_direct_reads_deduplicate_aliases(local_vault):
    write_lesson(local_vault, "Case-lesson-01")
    found = local_vault.read_and_bump(["Case-lesson-01", "CASE-LESSON-01"])
    assert len(found) == 1
    assert local_vault.get("Case-lesson-01").use_count == 1


@pytest.mark.skipif(os.name == "nt", reason="Case-sensitive POSIX filenames")
def test_posix_distinct_case_files_both_read_and_count(local_vault):
    first = write_lesson(local_vault, "Case", "FIRST advice")
    second = write_lesson(local_vault, "case", "SECOND advice")
    if first.samefile(second):
        pytest.skip("This filesystem ignores filename case")
    output, status = api._memory_read_result(["Case", "case"], local_vault)
    assert status == 0
    assert "FIRST advice" in output and "SECOND advice" in output
    assert local_vault.get("Case").use_count == 1
    assert local_vault.get("case").use_count == 1


@pytest.mark.parametrize("lesson_id", ["manual..notes", "release...notes"])
def test_internal_double_dots_are_queryable_and_readable(local_vault, lesson_id):
    write_lesson(local_vault, lesson_id, "distinctive double dot advice")
    assert lesson_id in api.memory_query("distinctive", vault=local_vault)
    output, status = api._memory_read_result(lesson_id, local_vault)
    assert status == 0
    assert "distinctive double dot advice" in output
    assert local_vault.get(lesson_id).use_count == 1


@pytest.mark.parametrize(
    "lesson_id",
    ["../outside", "..\\outside", "folder/../outside", "C:\\outside", "C:outside"],
)
def test_traversal_and_absolute_ids_still_cannot_read_outside(local_vault, lesson_id):
    outside = local_vault.case_dir / "outside.md"
    outside.write_text("---\ncase_id: outside\n---\nPRIVATE advice\n", encoding="utf-8")
    before = outside.read_bytes()
    output, status = api._memory_read_result(lesson_id, local_vault)
    assert status == 2
    assert "Not found:" in output
    assert "PRIVATE advice" not in output
    assert outside.read_bytes() == before


@pytest.mark.parametrize(
    ("ids", "status", "reads"),
    [(["present"], 0, 1), (["present", "missing"], 1, 1), (["missing"], 2, 0), ([], 2, 0)],
)
def test_read_status_has_no_second_read(local_vault, ids, status, reads):
    write_lesson(local_vault, "present")
    output, actual = api._memory_read_result(ids, local_vault)
    assert isinstance(output, str)
    assert actual == status
    assert local_vault.get("present").use_count == reads


def test_read_limit_refuses_without_counting(local_vault):
    write_lesson(local_vault, "present")
    output, status = api._memory_read_result(["present"] + [f"missing-{i}" for i in range(10)], local_vault)
    assert status == 2
    assert "at most 10" in output
    assert local_vault.get("present").use_count == 0


def test_uninitialized_read_status_is_two(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(tmp_path / "missing"))
    output, status = api._memory_read_result("missing")
    assert status == 2
    assert "agentbrain init" in output


def test_public_read_stays_plain_text(local_vault):
    write_lesson(local_vault, "present")
    output = api.memory_read("present", local_vault)
    assert isinstance(output, str) and "Useful guidance" in output
    assert local_vault.get("present").use_count == 1


def test_ingest_multiline_tags_cannot_forge_log_entries(local_vault):
    injected = "ops\n## [2099-01-01] ingest | invented-lesson-01"
    expected = "ops ## [2099-01-01] ingest | invented-lesson-01"
    result = api.memory_ingest(
        "real", "Validated advice", tags=[injected, "ops\r\nteam", "ops team"], vault=local_vault,
    )
    assert result.startswith("Saved ")
    assert local_vault.get("real-lesson-01").tags == [expected, "ops team"]
    entries = local_vault.log_entries()
    assert len(entries) == 1
    assert entries[0]["object"] == "real-lesson-01"
    assert entries[0]["tags"] == [expected, "ops team"]
    assert len(local_vault.log_md.read_text(encoding="utf-8").splitlines()) == 1
    assert "Nothing to distill" in api.memory_distill(vault=local_vault)


def test_log_fields_roundtrip_delimiters_unicode_and_literal_percent(local_vault):
    action = "verify\nnot-another-entry"
    obj = "name | literal %2C\r\nnext"
    tags = ["comma,tag", "pipe|tag", "部署", "literal%2C", "line\u2028break"]
    local_vault.append_log(action, obj, tags)
    assert len(local_vault.log_md.read_text(encoding="utf-8").splitlines()) == 1
    assert local_vault.log_entries() == [{
        "date": dt.date.today().isoformat(), "action": action, "object": obj, "tags": tags,
    }]


def test_legacy_log_still_reads_literal_percent_without_decoding(local_vault):
    local_vault.log_md.write_text(
        "## [2026-01-01] ingest | case%2C-lesson-01 | tags:plain,%2C,部署\n",
        encoding="utf-8",
    )
    assert local_vault.log_entries() == [{
        "date": "2026-01-01", "action": "ingest", "object": "case%2C-lesson-01",
        "tags": ["plain", "%2C", "部署"],
    }]


def test_distill_preserves_comma_tags_as_one_topic(local_vault):
    for index in range(3):
        api.memory_ingest(f"case-{index}", f"Distinct verified advice {index}", tags=["alpha,beta"], vault=local_vault)
    output = api.memory_distill(vault=local_vault)
    assert "tag `alpha,beta` appeared 3" in output
    assert "tag `alpha`" not in output and "tag `beta`" not in output


def test_distill_excludes_future_entries_and_keeps_today(local_vault):
    today = dt.date.today()
    future = today + dt.timedelta(days=1)
    local_vault.log_md.write_text(
        "".join(f"## [{future}] ingest | future-lesson-{i:02d}\n" for i in range(3))
        + f"## [{today}] ingest | current-lesson-01\n",
        encoding="utf-8",
    )
    assert "Nothing to distill" in api.memory_distill(vault=local_vault)
    output = api.memory_distill(min_repeat=1, vault=local_vault)
    assert "1 ingests" in output
    assert "current" in output and "future" not in output


def test_stats_explains_cumulative_counts_without_writes(local_vault):
    path = write_lesson(local_vault, "old", count=7)
    before = path.read_bytes()
    output = api.memory_stats(vault=local_vault)
    assert "total recorded reads: 7" in output
    assert "Counters are cumulative" in output
    assert "do not establish recent use or adoption" in output
    assert path.read_bytes() == before
    assert not local_vault.log_md.exists()


def test_simple_logs_keep_the_existing_readable_format(local_vault):
    local_vault.append_log("ingest", "plain-lesson-01", ["ops", "部署"])
    assert local_vault.log_md.read_text(encoding="utf-8") == (
        f"## [{dt.date.today()}] ingest | plain-lesson-01 | tags:ops,部署\n"
    )
