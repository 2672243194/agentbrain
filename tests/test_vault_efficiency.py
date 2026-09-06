from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

from agentbrain.frontmatter import parse, parse_document
from agentbrain import vault as vault_module
from agentbrain.vault import Vault


@pytest.fixture
def isolated_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    return vault


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_read_count_preserves_handwritten_document(isolated_vault, newline, bom):
    path = isolated_vault.learnings_dir / "handwritten.md"
    original = bom + (
        "---\n# owner comment\ncase_id: handwritten\n"
        "source_summary: 'precise summary'\n"
        "custom: {owner: someone, options: [a, b]}\n"
        "use_count: 7  # actual reads\n---\n\n"
        "  Indented Markdown\n\n```yaml\nuse_count: 100\n```\n\n"
    ).replace("\n", newline)
    path.write_bytes(original.encode("utf-8"))

    isolated_vault.bump_use(["handwritten"])

    assert path.read_bytes() == original.replace(
        "use_count: 7", "use_count: 8", 1
    ).encode("utf-8")


def test_repeated_ids_increment_once(isolated_vault):
    path = isolated_vault.learnings_dir / "once.md"
    path.write_text("---\ncase_id: once\nuse_count: 0\n---\nbody", encoding="utf-8")
    isolated_vault.bump_use(["once", "once", "missing"])
    assert isolated_vault.get("once").use_count == 1


def test_unreadable_encoding_does_not_break_other_lessons(isolated_vault):
    good = isolated_vault.learnings_dir / "good.md"
    good.write_text("---\ncase_id: good\n---\nbody", encoding="utf-8")
    broken = isolated_vault.learnings_dir / "invalid.md"
    broken.write_bytes(b"---\ncase_id: \xff\n---\nbody")
    assert [lesson.lesson_id for lesson in isolated_vault.lessons()] == ["good"]
    assert broken in isolated_vault.broken_lessons()


@pytest.mark.parametrize("value", [".inf", "-.inf", ".nan"])
def test_invalid_numeric_values_do_not_poison_reads(isolated_vault, value):
    path = isolated_vault.learnings_dir / "numeric.md"
    path.write_text(
        f"---\ncase_id: numeric\nconfidence: {value}\nuse_count: {value}\n---\nbody",
        encoding="utf-8",
    )
    loaded = isolated_vault.get("numeric")
    assert loaded.use_count == 0
    assert loaded.confidence == 0.8


def test_frontmatter_delimiter_is_a_complete_line():
    text = "---\ncase_id: example\n---not-a-delimiter\n\nbody"
    assert parse(text) == ({}, text)


def test_frontmatter_preserves_leading_body_whitespace():
    text = "---\ncase_id: example\n---\n\n    indented code\n"
    assert parse(text)[1] == "\n    indented code\n"


@pytest.mark.parametrize("header", ["case_id: \x00", "created_at: 2026-99-99"])
def test_invalid_handwritten_yaml_is_reported_without_crashing(isolated_vault, header):
    path = isolated_vault.learnings_dir / "invalid.md"
    path.write_text(f"---\n{header}\n---\nbody", encoding="utf-8")
    assert isolated_vault.get("invalid") is None
    assert isolated_vault.broken_lessons() == [path]


@pytest.mark.parametrize(
    "header, expected",
    [
        ("case_id: c\n'use_count': '7' # note\n", "case_id: c\n'use_count': '8' # note\n"),
        ('case_id: c\n"use_count": "7"\n', 'case_id: c\n"use_count": "8"\n'),
        ("{case_id: c, use_count: 7, other: 9}\n", "{case_id: c, use_count: 8, other: 9}\n"),
        ("case_id: c\ncustom:\n  use_count: 9\n", "case_id: c\ncustom:\n  use_count: 9\nuse_count: 1\n"),
        ("{case_id: c}\n", "{case_id: c, use_count: 1}\n"),
        ("{case_id: c,}\n", "{case_id: c, use_count: 1}\n"),
        ("{case_id: c, # end\n}\n", "{case_id: c, # end\n use_count: 1}\n"),
        ("case_id: c\n...\n", "case_id: c\nuse_count: 1\n...\n"),
        ("  case_id: c\n", "  case_id: c\n  use_count: 1\n"),
        ("case_id: c\nuse_count:\n", "case_id: c\nuse_count: 1\n"),
        ("case_id: c\nuse_count: |\n  7\n", "case_id: c\nuse_count: 8\n"),
        ("case_id: c\nuse_count: 3\nuse_count: 7\n", "case_id: c\nuse_count: 3\nuse_count: 8\n"),
        ("case_id: c\ncustom: &counter 7\nuse_count: *counter\n", "case_id: c\ncustom: &counter 7\nuse_count: 8\n"),
        ("case_id: c\ndefaults: &defaults {use_count: 7}\n<<: *defaults\n", "case_id: c\ndefaults: &defaults {use_count: 7}\n<<: *defaults\nuse_count: 8\n"),
    ],
)
def test_counter_updates_only_its_top_level_yaml_value(isolated_vault, header, expected):
    path = isolated_vault.learnings_dir / "yaml.md"
    path.write_bytes(("---\n" + header + "---\nbody\n").encode("utf-8"))
    isolated_vault.bump_use(["yaml"])
    assert path.read_bytes() == ("---\n" + expected + "---\nbody\n").encode("utf-8")
    assert isolated_vault.get("yaml").use_count in (1, 8)


def test_counter_anchor_does_not_change_unrelated_metadata(isolated_vault):
    path = isolated_vault.learnings_dir / "anchor.md"
    original = b"---\ncase_id: c\nuse_count: &counter 7\ncustom: *counter\n---\nbody"
    path.write_bytes(original)
    assert isolated_vault.read_and_bump(["anchor"])[0].content == "body"
    assert path.read_bytes() == original


def test_read_and_bump_reads_and_parses_each_lesson_once(isolated_vault, monkeypatch):
    path = isolated_vault.learnings_dir / "efficient.md"
    path.write_text("---\ncase_id: c\nuse_count: 0\n---\nbody", encoding="utf-8")
    real_open = type(path).open
    real_parse = vault_module.parse_document
    reads, parses = [], []

    def counted_open(self, *args, **kwargs):
        if self == path and (not args or args[0] == "r"):
            reads.append(self)
        return real_open(self, *args, **kwargs)

    def counted_parse(text):
        parses.append(text)
        return real_parse(text)

    monkeypatch.setattr(type(path), "open", counted_open)
    monkeypatch.setattr(vault_module, "parse_document", counted_parse)
    lessons = isolated_vault.read_and_bump(["efficient", "efficient"])
    assert [lesson.lesson_id for lesson in lessons] == ["efficient"]
    assert len(reads) == len(parses) == 1
    assert lessons[0].use_count == 0


def test_independent_vault_instances_do_not_lose_concurrent_counts(isolated_vault):
    path = isolated_vault.learnings_dir / "parallel.md"
    path.write_text("---\ncase_id: c\nuse_count: 0\n---\nbody", encoding="utf-8")

    def record_read(_):
        Vault(isolated_vault.root).read_and_bump(["parallel"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(record_read, range(18)))
    assert isolated_vault.get("parallel").use_count == 18


def test_read_observes_external_edit_replace_and_deletion(isolated_vault):
    path = isolated_vault.learnings_dir / "fresh.md"
    path.write_text("---\ncase_id: c\n---\nfirst", encoding="utf-8")
    assert isolated_vault.get("fresh").content == "first"
    other = Vault(isolated_vault.root)
    path.write_text("---\ncase_id: c\n---\nedited", encoding="utf-8")
    assert other.read_and_bump(["fresh"])[0].content == "edited"
    replacement = path.with_name("replacement.md")
    replacement.write_text("---\ncase_id: c\n---\nreplaced", encoding="utf-8")
    replacement.replace(path)
    assert isolated_vault.read_and_bump(["fresh"])[0].content == "replaced"
    path.unlink()
    assert isolated_vault.get("fresh") is None
    assert other.read_and_bump(["fresh"]) == []


@pytest.mark.parametrize("metadata", ["superseded_by: new", f"valid_until: {dt.date.today()}"])
def test_obsolete_lessons_are_read_without_reinforcing_use(isolated_vault, metadata):
    path = isolated_vault.learnings_dir / "obsolete.md"
    original = f"---\ncase_id: c\nuse_count: 3\n{metadata}\n---\nbody"
    path.write_bytes(original.encode("utf-8"))
    assert isolated_vault.read_and_bump(["obsolete"])[0].content == "body"
    assert path.read_bytes() == original.encode("utf-8")


def test_invalid_filename_is_reported_as_missing(isolated_vault):
    assert isolated_vault.get("nul\x00name") is None
    assert isolated_vault.read_and_bump(["nul\x00name"]) == []


@pytest.mark.parametrize(
    "lesson_id",
    [
        "CON", "con.txt", "NUL", "AUX", "PRN", "COM1", "LPT9",
        "COM¹", "LPT³", "CONIN$", "CONOUT$", "safe:stream",
        "nul\x00name", "control\x01name", "line\nbreak", "tab\tname",
        "delete\x7fname", "../outside", "nested/name", "nested\\name",
    ],
)
def test_unsafe_lesson_names_never_open_a_file(isolated_vault, monkeypatch, lesson_id):
    def forbidden_open(*args, **kwargs):
        pytest.fail("Unsafe lesson name reached Path.open")

    monkeypatch.setattr(type(isolated_vault.root), "open", forbidden_open)
    assert isolated_vault.get(lesson_id) is None
    assert isolated_vault.read_and_bump([lesson_id]) == []
    # Direct load_lesson callers also reject device names before opening.
    if "/" not in lesson_id and "\\" not in lesson_id:
        assert isolated_vault.load_lesson(isolated_vault.learnings_dir / f"{lesson_id}.md") is None


def test_read_document_never_opens_non_regular_files(isolated_vault, monkeypatch):
    directory = isolated_vault.learnings_dir / "directory.md"
    directory.mkdir()

    def forbidden_open(*args, **kwargs):
        pytest.fail("Non-file reached Path.open")

    monkeypatch.setattr(type(directory), "open", forbidden_open)
    assert isolated_vault.load_lesson(directory) is None
    assert isolated_vault.load_lesson(directory.with_name("missing.md")) is None

    # Simulate a device/FIFO without creating or opening any actual device.
    monkeypatch.setattr(type(directory), "is_file", lambda self: False)
    assert isolated_vault.load_lesson(directory.with_name("special.md")) is None


@pytest.mark.parametrize("python_fallback", [False, True])
def test_safe_loader_backends_preserve_unicode_source_marks(monkeypatch, python_fallback):
    if python_fallback:
        monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    elif not hasattr(yaml, "CSafeLoader"):
        pytest.skip("Optional LibYAML extension is unavailable")
    text = (
        "\ufeff---\r\ncase_id: unicode\r\n"
        "source_summary: '中文经验 🧠 café'\r\n"
        "custom: {owner: '张三', use_count: 99}\r\n"
        '"use_count": "7" # 原注释\r\n---\r\n\r\n    正文\r\n'
    )
    document = parse_document(text)
    assert document.meta["source_summary"] == "中文经验 🧠 café"
    assert document.with_integer("use_count", 8) == text.replace(
        '"use_count": "7"', '"use_count": "8"'
    )


def test_python_safe_loader_fallback_is_used(monkeypatch):
    monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    original = yaml.SafeLoader
    calls = []

    def tracked_loader(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(yaml, "SafeLoader", tracked_loader)
    document = parse_document("---\ncase_id: fallback\n---\nbody")
    assert document.meta == {"case_id": "fallback"}
    assert document.with_integer("use_count", 1) == (
        "---\ncase_id: fallback\nuse_count: 1\n---\nbody"
    )
    assert calls == ["case_id: fallback\n"]
