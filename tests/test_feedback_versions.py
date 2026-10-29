"""Content identity must survive telemetry writes and process restarts."""
from pathlib import Path
import subprocess
import sys

from agentbrain import api
from agentbrain.frontmatter import parse_document
from agentbrain.vault import Vault


def version(text):
    return Vault._lesson_from_document(Path("example.md"), parse_document(text)).version


def test_markdown_code_indentation_changes_version():
    header = "---\ncase_id: example\n---\n"
    assert version(header + "    print(1)") != version(header + "print(1)")


def test_custom_yaml_sets_and_aliases_are_stable_across_hash_seeds():
    source = (
        "---\ncase_id: example\nuse_count: 3\n"
        "environments: !!set {linux: null, windows: null, macos: null, 1: null}\n"
        "custom: &conditions {self: *conditions, flag: true, date: 2026-10-29}\n"
        "---\n    Indented instructions\n"
    )
    expected = version(source)
    assert len(expected) == 64
    # -I ignores PYTHONHASHSEED; random process hash seeds deliberately exercise
    # unordered YAML sets while importing only the isolated editable install.
    script = (
        "from pathlib import Path; from agentbrain.frontmatter import parse_document; "
        "from agentbrain.vault import Vault; "
        f"print(Vault._lesson_from_document(Path('example.md'),parse_document({source!r})).version)"
    )
    for _ in range(4):
        result = subprocess.run([sys.executable, "-I", "-c", script],
                                check=True, capture_output=True, text=True, timeout=20)
        assert result.stdout.strip() == expected


def test_metadata_order_and_telemetry_do_not_change_content_identity():
    first = "---\ncase_id: example\nuse_count: 1\ncustom: {b: 2, a: 1}\n---\nbody"
    reordered = "---\ncustom: {a: 1, b: 2}\nlast_verified_at: 2026-10-29\nuse_count: 99\ncase_id: example\n---\nbody"
    assert version(first) == version(reordered)
    assert version(first) != version(first.replace("b: 2", "b: 3"))


def test_explicit_uninitialized_vault_does_not_create_lock_or_directory(tmp_path):
    vault = Vault(tmp_path / "missing")
    output = api.memory_feedback("task", [{
        "lesson_id": "example", "lesson_version": "0" * 64, "outcome": "unverified",
        "environment": "Local test", "evidence": "No result yet.",
    }], vault=vault)
    assert output.startswith("Refused:")
    assert not vault.root.exists()
