from agentbrain.vault import Vault


def test_init_creates_layout(vault: Vault, tmp_path):
    root = tmp_path / "vault"
    assert (root / "AGENTS.md").is_file()
    assert (root / "ONBOARDING.md").is_file()
    assert (root / "Case-Learnings" / "Index.md").is_file()
    assert (root / "Case-Learnings" / "log.md").is_file()
    assert (root / "Case-Learnings" / "Learnings").is_dir()
    assert (root / "Case-Learnings" / "_consolidations").is_dir()
    assert (root / "Agent-Profile" / "Immutable" / "profile.md").is_file()
    assert (root / "Agent-Profile" / "Mutable-Hints").is_dir()
    assert (root / "Agent-Profile" / "_suggestions").is_dir()


def test_ingest_persists_file_index_log(vault: Vault):
    lesson = vault.new_lesson("case-001", "证据当天固定", "内容", ["证据"])
    vault.save(lesson, action="ingest")
    p = vault.learnings_dir / "case-001-lesson-01.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "case_id: case-001" in text
    assert "证据当天固定" in text
    assert "case-001-lesson-01" in vault.index_md.read_text(encoding="utf-8")
    assert "ingest | case-001-lesson-01" in vault.log_md.read_text(encoding="utf-8")


def test_next_lesson_id_increments(vault: Vault):
    assert vault.next_lesson_id("case-001") == "case-001-lesson-01"
    vault.save(vault.new_lesson("case-001", "s", "c", []), action="ingest")
    assert vault.next_lesson_id("case-001") == "case-001-lesson-02"


def test_lessons_roundtrip_and_superseded_filter(vault: Vault):
    a = vault.new_lesson("c1", "s1", "content one", ["t"])
    vault.save(a, action="ingest")
    b = vault.new_lesson("c2", "s2", "content two", ["t"])
    vault.save(b, action="ingest")
    b.superseded_by = a.lesson_id
    vault.save(b)

    active_ids = [l.lesson_id for l in vault.lessons()]
    assert a.lesson_id in active_ids
    assert b.lesson_id not in active_ids
    assert b.lesson_id in [l.lesson_id for l in vault.lessons(include_superseded=True)]


def test_log_entries_parse(vault: Vault):
    vault.save(vault.new_lesson("c1", "s", "c", ["a", "b"]), action="ingest")
    entries = vault.log_entries()
    ingest = [e for e in entries if e["action"] == "ingest"]
    assert len(ingest) == 1
    assert ingest[0]["object"] == "c1-lesson-01"
    assert ingest[0]["tags"] == ["a", "b"]


def test_load_lesson_tolerates_bad_numeric_frontmatter(vault: Vault):
    good = vault.new_lesson("c1", "good summary", "good content", ["t"])
    vault.save(good, action="ingest")
    bad = vault.learnings_dir / "hand-edited-lesson-01.md"
    bad.write_text(
        "---\ncase_id: hand-edited\nsource_summary: hand edit\ntags: [t]\n"
        "confidence: high\nuse_count: many\n---\n\nbody\n",
        encoding="utf-8",
    )
    lessons = vault.lessons()  # one bad file must not poison vault reads
    ids = [l.lesson_id for l in lessons]
    assert "hand-edited-lesson-01" in ids
    loaded = vault.get("hand-edited-lesson-01")
    assert loaded is not None
    assert loaded.confidence == 0.8
    assert loaded.use_count == 0
