"""The health report checks membership in the index's lesson column."""
from agentbrain import cli
from agentbrain.doctor import doctor


def test_doctor_detects_missing_id_despite_longer_id_and_summary_mentions(vault, capsys):
    for lesson_id in ("guide", "guide-extra"):
        (vault.learnings_dir / f"{lesson_id}.md").write_text(
            "---\ncase_id: checks\nsource_summary: guide\n---\nInstructions.\n",
            encoding="utf-8",
        )
    vault.rebuild_index()
    rows = vault.index_md.read_text(encoding="utf-8").splitlines()
    vault.index_md.write_text("\n".join(row for row in rows if not row.startswith("| guide |")) + "\n",
                              encoding="utf-8")
    before = vault.index_md.read_bytes()
    assert "index: STALE" in doctor(vault)
    assert cli.main(["--vault", str(vault.root), "doctor"]) == 1
    assert "1 lesson(s) missing" in capsys.readouterr().out
    assert vault.index_md.read_bytes() == before
    vault.rebuild_index()
    assert "index: fresh" in doctor(vault)


def test_doctor_accepts_complete_ids_with_variable_table_spacing(vault):
    (vault.learnings_dir / "guide.md").write_text("---\ncase_id: checks\n---\nBody\n", encoding="utf-8")
    vault.rebuild_index()
    text = vault.index_md.read_text(encoding="utf-8")
    vault.index_md.write_text(text.replace("| guide |", "|guide|"), encoding="utf-8")
    assert "index: fresh" in doctor(vault)
