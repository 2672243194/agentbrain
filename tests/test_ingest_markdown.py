"""Markdown whitespace survives lesson ingestion and full-text reads."""
import subprocess
import sys

import pytest

from agentbrain import api
from agentbrain.frontmatter import dump, parse_document
from agentbrain.vault import Vault


@pytest.fixture
def local_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.learnings_dir.mkdir(parents=True)
    return vault


def normalize_newlines(text):
    return text.replace("\r\n", "\n")


@pytest.mark.parametrize("body", [
    "    print('first line')\n    print('second line')",
    "```python\n    print('indented statement')\n```  ",
    "First line  \nSecond line  ",
    "第一行普通文本\r\n第二行普通文本",
])
def test_api_ingest_preserves_markdown_in_saved_body_and_full_reads(local_vault, body):
    result = api.memory_ingest("whitespace", body, source_summary="Markdown guidance", vault=local_vault)
    assert result.startswith("Saved whitespace-lesson-01")
    lesson = local_vault.get("whitespace-lesson-01")
    expected = normalize_newlines(body)
    assert normalize_newlines(lesson.content) == expected
    for output in (
        api.memory_read([lesson.lesson_id], vault=local_vault),
        api.memory_query("Markdown", mode="full", vault=local_vault),
    ):
        assert normalize_newlines(output).endswith("\n\n" + expected)
    assert local_vault.get(lesson.lesson_id).use_count == 2


def test_cli_ingest_and_read_preserve_indented_body_and_final_spaces(local_vault):
    body = "    print('first line')\n    print('second line')  "
    arguments = [sys.executable, "-I", "-m", "agentbrain", "--vault", str(local_vault.root)]
    ingested = subprocess.run(
        [*arguments, "ingest", "--case", "cli-markdown", "--lesson", body],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert ingested.returncode == 0, ingested.stderr
    read = subprocess.run(
        [*arguments, "read", "cli-markdown-lesson-01"],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert read.returncode == 0, read.stderr
    assert read.stdout.endswith("\n\n" + body + "\n")
    assert normalize_newlines(local_vault.get("cli-markdown-lesson-01").content) == body


@pytest.mark.parametrize("body", [
    "\r\n    print('code')  \r\n",
    "\nParagraph with a hard break  \n",
    "\r\n    First indented line  \r\n    Second line\nFinal line  \r\n",
])
def test_frontmatter_dump_only_trims_boundary_newlines(body):
    document = parse_document(dump({"case_id": "markdown"}, body))
    assert document.body == "\n" + normalize_newlines(body).strip("\r\n") + "\n"
