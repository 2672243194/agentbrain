import agentbrain.api as api
from agentbrain.profile import Profile
from agentbrain.vault import Vault


def test_read_merges_layers_and_skips_readme(vault: Vault):
    (vault.root / "Agent-Profile" / "Mutable-Hints" / "hints.md").write_text(
        "# Hints\n\n- prefers bullet lists\n", encoding="utf-8"
    )
    text = Profile(vault).read()
    assert "[immutable] profile" in text
    assert "[hints] hints" in text
    assert "prefers bullet lists" in text
    assert "README" not in text


def test_read_empty_when_no_profile_files(vault: Vault):
    (vault.root / "Agent-Profile" / "Immutable" / "profile.md").unlink()
    assert Profile(vault).read() == ""


def test_suggest_writes_pending_file(vault: Vault):
    path = Profile(vault).suggest("Reply in English", "User switched to English; default to English replies.")
    assert path.parent == vault.root / "Agent-Profile" / "_suggestions"
    text = path.read_text(encoding="utf-8")
    assert "title: Reply in English" in text
    assert "status: pending" in text
    assert "English replies" in text


def test_api_memory_profile(vault: Vault):
    out = api.memory_profile(vault=vault)
    assert "[immutable] profile" in out


def test_api_memory_suggest_logs(vault: Vault):
    out = api.memory_suggest(title="更简洁", change="回复控制在三句话以内", vault=vault)
    assert "Suggestion saved" in out
    assert "_suggestions/" in out
    assert "suggest | Agent-Profile/_suggestions/" in vault.log_md.read_text(encoding="utf-8")


def test_api_memory_suggest_refuses_empty(vault: Vault):
    assert "Refused" in api.memory_suggest(title="", change="x", vault=vault)
    assert "Refused" in api.memory_suggest(title="t", change=" ", vault=vault)


def test_api_memory_profile_empty_hint(vault: Vault):
    (vault.root / "Agent-Profile" / "Immutable" / "profile.md").unlink()
    assert "Profile is empty" in api.memory_profile(vault=vault)
