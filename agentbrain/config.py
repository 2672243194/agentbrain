from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VAULT_NAME = "agentbrain"
ENV_VAR = "AGENTBRAIN_VAULT"


@dataclass
class Config:
    vault_dir: Path

    @classmethod
    def load(cls, vault: str | Path | None = None) -> "Config":
        root = vault or os.environ.get(ENV_VAR) or Path.home() / DEFAULT_VAULT_NAME
        return cls(vault_dir=Path(root).expanduser().resolve())
