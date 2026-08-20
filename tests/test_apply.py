import pytest

import agentbrain.api as api
from agentbrain.apply import ProposalError, apply_proposal, parse_directives
from agentbrain.vault import Vault


def _lint_for_duplicates(vault: Vault) -> str:
    api.memory_ingest(case_id="c1", lesson="always pin dependencies in requirements.txt", tags=["deps"], source_summary="pin dependencies", vault=vault)
    api.memory_ingest(case_id="c2", lesson="always pin your dependencies in the requirements file", tags=["deps"], source_summary="pin dependencies exactly", vault=vault)
    api.memory_lint(vault=vault)
    proposals = [p for p in vault.consolidations_dir.glob("lint-*.md") if not p.stem.endswith(".applied")]
    assert len(proposals) == 1
    return proposals[0].name


def test_parse_directives():
    text = (
        "prose\n```agentbrain\nsupersede: a-lesson-01 -> b-lesson-01\n```\n"
        "more prose\n```agentbrain\nignored line\nsupersede: x -> y\n```\n"
    )
    assert parse_directives(text) == [("a-lesson-01", "b-lesson-01"), ("x", "y")]
    assert parse_directives("no directives here") == []


def test_apply_supersedes_and_archives(vault: Vault):
    name = _lint_for_duplicates(vault)
    report = apply_proposal(vault, name)
    assert "Applied 1 directive(s)" in report
    assert "→ c1-lesson-01" in report

    superseded = vault.get("c2-lesson-01")
    assert superseded.superseded_by == "c1-lesson-01"
    assert "c2-lesson-01" not in [l.lesson_id for l in vault.lessons()]
    assert "apply |" in vault.log_md.read_text(encoding="utf-8")
    assert not (vault.consolidations_dir / name).exists()
    applied = list(vault.consolidations_dir.glob("*.applied.md"))
    assert len(applied) == 1


def test_apply_twice_refuses(vault: Vault):
    name = _lint_for_duplicates(vault)
    apply_proposal(vault, name)
    applied = next(p for p in vault.consolidations_dir.glob("*.md") if p.stem.endswith(".applied"))
    with pytest.raises(ProposalError, match="already applied"):
        apply_proposal(vault, applied.name)


def test_apply_missing_file(vault: Vault):
    with pytest.raises(ProposalError, match="not found"):
        apply_proposal(vault, "nope.md")


def test_apply_invalid_directive_is_transactional(vault: Vault, tmp_path):
    name = _lint_for_duplicates(vault)
    path = vault.consolidations_dir / name
    path.write_text(
        "```agentbrain\nsupersede: c2-lesson-01 -> c1-lesson-01\n"
        "supersede: ghost-lesson -> c1-lesson-01\n```\n",
        encoding="utf-8",
    )
    with pytest.raises(ProposalError, match="ghost-lesson"):
        apply_proposal(vault, name)
    assert vault.get("c2-lesson-01").superseded_by == ""
    assert path.exists()


def test_apply_self_supersede_refused(vault: Vault):
    path = vault.consolidations_dir / "lint-self.md"
    path.write_text("```agentbrain\nsupersede: a -> a\n```\n", encoding="utf-8")
    with pytest.raises(ProposalError, match="self-supersede"):
        apply_proposal(vault, path.name)


def test_apply_cycle_refused(vault: Vault):
    api.memory_ingest(case_id="c1", lesson="lesson one content", tags=["t"], vault=vault)
    api.memory_ingest(case_id="c2", lesson="lesson two content", tags=["t"], vault=vault)
    a = vault.get("c1-lesson-01")
    a.superseded_by = "c2-lesson-01"
    vault.save(a)
    path = vault.consolidations_dir / "lint-cycle.md"
    path.write_text("```agentbrain\nsupersede: c2-lesson-01 -> c1-lesson-01\n```\n", encoding="utf-8")
    with pytest.raises(ProposalError, match="cycle"):
        apply_proposal(vault, path.name)


def test_apply_no_directives(vault: Vault):
    path = vault.consolidations_dir / "distill-x.md"
    path.write_text("# Distill proposal\n\nGuidance only, no machine directives.\n", encoding="utf-8")
    with pytest.raises(ProposalError, match="No 'supersede' directives"):
        apply_proposal(vault, path.name)


def test_cli_apply_flow(vault: Vault, capsys):
    from agentbrain import cli

    name = _lint_for_duplicates(vault)
    rc = cli.main(["--vault", str(vault.root), "apply", name])
    assert rc == 0
    assert "Applied 1 directive(s)" in capsys.readouterr().out


def test_cli_apply_error_exit_code(vault: Vault, capsys):
    from agentbrain import cli

    rc = cli.main(["--vault", str(vault.root), "apply", "missing.md"])
    assert rc == 2
