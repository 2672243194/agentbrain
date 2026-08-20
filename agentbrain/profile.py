from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .vault import Vault

_UNSAFE = re.compile(r"[^A-Za-z0-9\u4e00-\u9fff-]+")


class Profile:
    """Read-only view of Agent-Profile plus the _suggestions write channel."""

    def __init__(self, vault: Vault):
        self.vault = vault
        self.immutable_dir = vault.root / "Agent-Profile" / "Immutable"
        self.hints_dir = vault.root / "Agent-Profile" / "Mutable-Hints"
        self.suggestions_dir = vault.root / "Agent-Profile" / "_suggestions"

    def _collect(self, directory: Path) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not directory.is_dir():
            return out
        for p in sorted(directory.glob("*.md")):
            if p.name.lower() == "readme.md":
                continue
            try:
                text = p.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                out.append((p.stem, text))
        return out

    def read(self) -> str:
        sections: list[str] = []
        for label, directory in (("immutable", self.immutable_dir), ("hints", self.hints_dir)):
            for stem, text in self._collect(directory):
                sections.append(f"## [{label}] {stem}\n\n{text}")
        return "\n\n".join(sections)

    def suggest(self, title: str, change: str) -> Path:
        slug = _UNSAFE.sub("-", (title or "").strip()).strip("-")[:40] or "suggestion"
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.suggestions_dir.mkdir(parents=True, exist_ok=True)
        path = self.suggestions_dir / f"{stamp}-{slug}.md"
        path.write_text(
            "---\n"
            f"title: {title.strip()}\n"
            f"created_at: {dt.date.today().isoformat()}\n"
            "status: pending\n"
            "---\n\n"
            f"{change.strip()}\n",
            encoding="utf-8",
        )
        return path
