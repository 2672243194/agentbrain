from __future__ import annotations

from contextlib import contextmanager

import pytest

from agentbrain.api import memory_lint
from agentbrain.apply import ProposalError, apply_proposal, parse_directives


def _lesson(
    vault, lesson_id, *, superseded_by="", use_count=0,
    summary="same guidance", valid_until="",
):
    path = vault.learnings_dir / f"{lesson_id}.md"
    path.write_text(
        f"---\ncase_id: {lesson_id}\nsource_summary: {summary}\n"
        f"tags: [guidance]\nuse_count: {use_count}\n"
        f"valid_until: '{valid_until}'\n"
        f"superseded_by: '{superseded_by}'\n---\n\n"
        "Preserve the reusable guidance and manually review its applicability.\n",
        encoding="utf-8",
    )
    return path


def _proposal(vault, *directives):
    path = vault.consolidations_dir / "lint-integrity.md"
    path.write_text(
        "```agentbrain\n"
        + "\n".join(f"supersede: {old} -> {new}" for old, new in directives)
        + "\n```\n",
        encoding="utf-8",
    )
    return path


def _markdown(vault):
    return {p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*.md")}


@pytest.mark.parametrize(
    "directives",
    [(("a", "b"), ("b", "a")), (("a", "b"), ("b", "c"), ("c", "a"))],
)
def test_apply_rejects_cycle_created_by_batch_without_writes(vault, directives):
    for lesson_id in ("a", "b", "c"):
        _lesson(vault, lesson_id)
    proposal = _proposal(vault, *directives)
    before = _markdown(vault)

    with pytest.raises(ProposalError, match="cycle"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before


def test_apply_rejects_multiple_targets_before_writing(vault):
    for lesson_id in ("a", "b", "c"):
        _lesson(vault, lesson_id)
    proposal = _proposal(vault, ("a", "b"), ("a", "c"))
    before = _markdown(vault)

    with pytest.raises(ProposalError, match="conflicting targets"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before


def test_apply_checks_final_graph_with_existing_edges(vault):
    _lesson(vault, "a")
    _lesson(vault, "b", superseded_by="c")
    _lesson(vault, "c")
    proposal = _proposal(vault, ("a", "b"), ("c", "a"))
    before = _markdown(vault)

    with pytest.raises(ProposalError, match="cycle"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before


def test_apply_rejects_dangling_replacement_chain_without_writes(vault):
    _lesson(vault, "a")
    _lesson(vault, "b", superseded_by="missing")
    proposal = _proposal(vault, ("a", "b"))
    before = _markdown(vault)

    with pytest.raises(ProposalError, match="missing target lesson: missing"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before


def test_apply_unrelated_dangling_lesson_does_not_block_valid_replacement(vault):
    _lesson(vault, "a")
    _lesson(vault, "b")
    _lesson(vault, "unrelated", superseded_by="missing")
    proposal = _proposal(vault, ("a", "b"))

    assert "Applied 1 directive(s)" in apply_proposal(vault, proposal)
    assert vault.get("a").superseded_by == "b"


def test_apply_revalidates_targets_after_acquiring_lock(vault, monkeypatch):
    _lesson(vault, "a")
    _lesson(vault, "b")
    proposal = _proposal(vault, ("a", "b"))
    original_lock = vault.locked
    before = {}

    @contextmanager
    def concurrent_change():
        with original_lock():
            _lesson(vault, "b", superseded_by="a")
            before.update(_markdown(vault))
            yield

    monkeypatch.setattr(vault, "locked", concurrent_change)

    with pytest.raises(ProposalError, match="cycle"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before


def test_apply_rechecks_all_sources_before_first_write(vault, monkeypatch):
    for lesson_id in ("a", "b", "c"):
        _lesson(vault, lesson_id)
    proposal = _proposal(vault, ("a", "c"), ("b", "c"))
    original_lock = vault.locked
    before = {}

    @contextmanager
    def concurrent_change():
        with original_lock():
            _lesson(vault, "b", superseded_by="c")
            before.update(_markdown(vault))
            yield

    monkeypatch.setattr(vault, "locked", concurrent_change)

    with pytest.raises(ProposalError, match="already superseded"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before


def test_apply_archive_collision_is_rejected_before_writes(vault):
    _lesson(vault, "a")
    _lesson(vault, "b")
    proposal = _proposal(vault, ("a", "b"))
    proposal.with_name("lint-integrity.applied.md").write_text(
        "Owner's prior approval record.\n", encoding="utf-8"
    )
    before = _markdown(vault)

    with pytest.raises(ProposalError, match="archive already exists"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before


def test_apply_deduplicates_identical_directives(vault):
    _lesson(vault, "a")
    _lesson(vault, "b")
    proposal = _proposal(vault, ("a", "b"), ("a", "b"))

    assert "Applied 1 directive(s)" in apply_proposal(vault, proposal)
    assert vault.get("a").superseded_by == "b"
    assert vault.get("b").superseded_by == ""


def test_lint_three_duplicates_produces_applicable_unambiguous_proposal(vault):
    for lesson_id, use_count in (("a", 1), ("b", 4), ("c", 10)):
        _lesson(vault, lesson_id, use_count=use_count)
    original = {p: p.read_bytes() for p in vault.learnings_dir.glob("*.md")}

    memory_lint(vault=vault)

    proposal = next(vault.consolidations_dir.glob("lint-*.md"))
    text = proposal.read_text(encoding="utf-8")
    directives = parse_directives(text)
    assert {p: p.read_bytes() for p in original} == original
    assert "Apply only after human approval" in text
    assert "by hand" in text
    assert set(directives) == {("a", "c"), ("b", "c")}
    assert "Applied 2 directive(s)" in apply_proposal(vault, proposal)
    assert {lesson.lesson_id for lesson in vault.lessons()} & {"a", "b", "c"} == {"c"}


def test_lint_does_not_infer_transitive_similarity(vault):
    for lesson_id, use_count, summary in (
        ("a", 10, "alpha bravo charlie delta echo"),
        ("b", 5, "alpha bravo charlie delta echo foxtrot"),
        ("c", 1, "bravo charlie delta echo foxtrot golf"),
    ):
        path = _lesson(vault, lesson_id, use_count=use_count, summary=summary)
        path.write_text(
            path.read_text(encoding="utf-8").replace("tags: [guidance]", "tags: []"),
            encoding="utf-8",
        )

    memory_lint(vault=vault)

    proposal = next(vault.consolidations_dir.glob("lint-*.md"))
    assert parse_directives(proposal.read_text(encoding="utf-8")) == [("b", "a")]
    assert "Applied 1 directive(s)" in apply_proposal(vault, proposal)
    assert vault.get("c").superseded_by == ""


def test_lint_keeps_available_lesson_instead_of_popular_expired_lesson(vault):
    _lesson(vault, "old", use_count=100, valid_until="2000-01-01")
    _lesson(vault, "current", use_count=1)

    report = memory_lint(vault=vault)

    assert "EXPIRED old" in report
    proposal = next(vault.consolidations_dir.glob("lint-*.md"))
    assert parse_directives(proposal.read_text(encoding="utf-8")) == [("old", "current")]
    assert "Applied 1 directive(s)" in apply_proposal(vault, proposal)
    assert vault.get("current").superseded_by == ""
    assert vault.get("old").superseded_by == "current"


def test_lint_does_not_generate_merges_with_only_expired_candidates(vault):
    _lesson(vault, "a", use_count=100, valid_until="2000-01-01")
    _lesson(vault, "b", use_count=1, valid_until="2000-01-01")

    report = memory_lint(vault=vault)

    assert "EXPIRED a" in report
    assert "EXPIRED b" in report
    proposal = next(vault.consolidations_dir.glob("lint-*.md"))
    assert parse_directives(proposal.read_text(encoding="utf-8")) == []


def test_apply_accepts_acyclic_batch_chains(vault):
    for lesson_id in ("a", "b", "c"):
        _lesson(vault, lesson_id)
    proposal = _proposal(vault, ("b", "c"), ("a", "b"))

    assert "Applied 2 directive(s)" in apply_proposal(vault, proposal)
    assert vault.get("a").superseded_by == "b"
    assert vault.get("b").superseded_by == "c"
    assert vault.get("c").superseded_by == ""


def test_apply_preserves_handwritten_markdown_and_metadata(vault):
    _lesson(vault, "keeper")
    path = vault.learnings_dir / "old.md"
    original = (
        "\ufeff---\r\ncase_id: old\r\n# owner comment\r\n"
        "custom: {owner: human, list: [one, two]}\r\n"
        "superseded_by: '' # approval\r\n---\r\n\r\n"
        "    Indented code\r\n\r\nOriginal trailing space  \r\n\r\n"
    ).encode("utf-8")
    path.write_bytes(original)
    proposal = _proposal(vault, ("old", "keeper"))

    apply_proposal(vault, proposal)

    updated = path.read_bytes()
    assert updated.replace(b"superseded_by: 'keeper'", b"superseded_by: ''", 1) == original
    assert vault.get("old").superseded_by == "keeper"


def test_apply_prepares_all_metadata_before_writing(vault):
    _lesson(vault, "a")
    _lesson(vault, "keeper")
    path = vault.learnings_dir / "b.md"
    path.write_text(
        "---\ncase_id: b\nsuperseded_by: &target ''\n"
        "custom: *target\n---\nOwner content\n",
        encoding="utf-8",
    )
    proposal = _proposal(vault, ("a", "keeper"), ("b", "keeper"))
    before = _markdown(vault)

    with pytest.raises(ProposalError, match="nothing applied"):
        apply_proposal(vault, proposal)

    assert _markdown(vault) == before
