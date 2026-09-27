"""Credential exemptions must cover complete values, including JSON input."""
from __future__ import annotations

import pytest

from agentbrain import api
from agentbrain.redact import scan


@pytest.mark.parametrize("text", [
    'password: sk-xxxxxxxxxxxxxxxx-SyntheticSecret12345',
    'password = ${ENV:KEY}SyntheticSecret12345',
    'password = SyntheticSecret12345${ENV:KEY}',
    'token = changeme-SyntheticSecret12345',
    'password=changeme,SyntheticSecret12345',
    'token=redacted;SyntheticSecret12345',
    'password="changeme,"',
    'api_key = <your-key>SyntheticSecret12345',
    '{"password": "LongSyntheticPassword12345"}',
    '{"password": "changeme LongSyntheticSecret12345"}',
    "password='redacted LongSyntheticSecret12345'",
    "{'api_key': 'LongSyntheticSecret12345'}",
    '"access-key": LongSyntheticSecret12345',
    '<sk-abc123def456ghi789jkl>',
])
def test_partial_placeholders_and_quoted_keys_do_not_hide_credentials(text):
    assert scan(text)


@pytest.mark.parametrize("text", [
    'password = ${ENV:PASSWORD}',
    'password = ${env:password}',
    '{"password": "${ENV:PASSWORD}"}',
    "{'api_key': '<your-key>'}",
    'password = <password>',
    'password = changeme, replace before deploying',
    'token=redacted; replace before deploying',
    'api_key = sk-xxxxxxxxxxxxxxxxxxxx',
    'token = redacted',
    'see pypi-publish-workflow-lesson-01',
    'Use ${ENV:THIS_IS_A_VERY_LONG_VARIABLE_NAME_FOR_KEYS} at runtime.',
])
def test_complete_teaching_placeholders_remain_allowed(text):
    assert scan(text) == []


@pytest.mark.parametrize("operation", ["ingest", "suggest"])
def test_credentials_are_refused_before_any_vault_write(vault, monkeypatch, operation):
    before = {p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*.md")}

    def forbidden(*args):
        pytest.fail("Refused input must not reach the Vault write lock")

    monkeypatch.setattr(vault, "locked", forbidden)
    content = '{"password": "LongSyntheticPassword12345"}'
    if operation == "ingest":
        result = api.memory_ingest("credential-example", content, vault=vault)
    else:
        result = api.memory_suggest("Credential example", content, vault=vault)
    assert result.startswith("Refused:")
    assert "LongSyntheticPassword12345" not in result
    after = {p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*.md")}
    assert after == before
