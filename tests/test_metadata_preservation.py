import datetime as dt

import pytest

from agentbrain.frontmatter import parse_document
from agentbrain.vault import Vault


@pytest.fixture
def local_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    return vault


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_verify_changes_only_date_and_preserves_handwritten_markdown(local_vault, newline, bom):
    original = bom + (
        "---\n# Owner metadata\ncase_id: handwritten\n"
        "last_verified_at: '2000-01-01' # Reviewed date\n"
        "custom: {owner: someone, keep: [a, b]}\nuse_count: 7\n"
        "---\n\n    Indented code\n\n```yaml\ncustom: retained\n```\n\n"
    ).replace("\n", newline)
    path = local_vault.learnings_dir / "handwritten.md"
    path.write_bytes(original.encode("utf-8"))

    assert local_vault.verify(["handwritten", "handwritten", "missing"]) == (["handwritten"], ["missing"])

    expected = original.replace("'2000-01-01'", repr(dt.date.today().isoformat()), 1)
    assert path.read_bytes() == expected.encode("utf-8")
    assert local_vault.get("handwritten").use_count == 7
    assert len(local_vault.log_entries()) == 1
    assert dt.date.today().isoformat() in local_vault.index_md.read_text(encoding="utf-8")


@pytest.mark.parametrize("header", [
    "{case_id: c, custom: retained}\n",
    "case_id: c\ncustom: retained\n...\n",
    "case_id: c\ncustom: &date '2000-01-01'\nlast_verified_at: *date\n",
    "case_id: c\ncustom: &defaults {last_verified_at: '2000-01-01'}\n<<: *defaults\n",
])
def test_verify_adds_or_overrides_date_without_changing_other_metadata(local_vault, header):
    path = local_vault.learnings_dir / "example.md"
    original = "---\n" + header + "---\n\n  Body stays indented\n"
    path.write_bytes(original.encode("utf-8"))
    before = parse_document(original)

    local_vault.verify(["example"])

    after = parse_document(path.read_text(encoding="utf-8"))
    assert after.body == before.body
    assert after.meta == dict(before.meta, last_verified_at=dt.date.today().isoformat())


@pytest.mark.parametrize("value", ["&date '2000-01-01'", "[2000-01-01]"])
def test_verify_validates_every_update_before_writing(local_vault, value):
    safe = local_vault.learnings_dir / "safe.md"
    unsafe = local_vault.learnings_dir / "unsafe.md"
    safe.write_text("---\ncase_id: safe\nlast_verified_at: '2000-01-01'\n---\nbody\n", encoding="utf-8")
    unsafe.write_text(f"---\ncase_id: unsafe\nlast_verified_at: {value}\n---\nbody\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (safe, unsafe)}

    with pytest.raises(ValueError, match="Cannot safely update last_verified_at"):
        local_vault.verify(["safe", "unsafe"])

    assert {path: path.read_bytes() for path in (safe, unsafe)} == before
    assert not local_vault.log_md.exists()
    assert not local_vault.index_md.exists()


def test_metadata_preparation_is_read_only(local_vault):
    path = local_vault.learnings_dir / "example.md"
    original = b"---\ncase_id: example\ncustom: kept\n---\n\nbody\n"
    path.write_bytes(original)
    with local_vault.locked():
        lesson, text = local_vault._prepare_metadata_update("example", {"superseded_by": "replacement"})
    assert lesson.superseded_by == "replacement"
    assert parse_document(text).meta["custom"] == "kept"
    assert path.read_bytes() == original


@pytest.mark.parametrize("target", ["new,case", "new[case]", "new{case}", "on", "null", "17"])
def test_apply_preserves_string_targets_inside_flow_yaml(local_vault, target):
    from agentbrain.apply import apply_proposal

    old = local_vault.learnings_dir / "old.md"
    old.write_text("---\n{case_id: old, custom: kept}\n---\n\n  Original body\n", encoding="utf-8")
    (local_vault.learnings_dir / f"{target}.md").write_text("---\ncase_id: target\n---\nreplacement\n", encoding="utf-8")
    local_vault.consolidations_dir.mkdir()
    proposal = local_vault.consolidations_dir / "flow.md"
    proposal.write_text(f"```agentbrain\nsupersede: old -> {target}\n```\n", encoding="utf-8")

    apply_proposal(local_vault, proposal)

    document = parse_document(old.read_text(encoding="utf-8"))
    assert document.meta == {"case_id": "old", "custom": "kept", "superseded_by": target}
    assert document.body == "\n  Original body\n"
