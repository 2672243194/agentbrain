import pytest

from agentbrain import scaffold
from agentbrain.vault import Vault


@pytest.fixture
def vault(tmp_path):
    scaffold.init(tmp_path / "vault")
    return Vault.open(root=tmp_path / "vault")
