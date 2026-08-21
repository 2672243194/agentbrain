from __future__ import annotations

import json
import sys

from . import __version__
from .config import Config
from .snapshot import Snapshot
from .vault import Vault, VaultNotInitialized


def _mcp_hint(vault_root: str) -> list[str]:
    env_value = json.dumps(vault_root)  # escaped backslashes on Windows
    return [
        "",
        "Paste this into any MCP client (Claude Code / Codex / Cursor / DSH):",
        "```json",
        "{",
        '  "mcpServers": {',
        '    "agentbrain": {',
        '      "command": "agentbrain",',
        '      "args": ["serve"],',
        f'      "env": {{ "AGENTBRAIN_VAULT": {env_value} }}',
        "    }",
        "  }",
        "}",
        "```",
    ]


def doctor(vault: Vault | None = None) -> str:
    """One-shot health report for humans. Read-only except a lock round-trip."""
    lines = [f"agentbrain {__version__} · Python {sys.version.split()[0]}"]
    problems: list[str] = []

    if vault is None:
        try:
            vault = Vault.open(Config.load())
        except VaultNotInitialized as e:
            lines.append(f"vault: NOT INITIALIZED — {e}")
            lines += _mcp_hint(str(Config.load().vault_dir))
            return "\n".join(lines)

    lines.append(f"vault: {vault.root}")

    lessons = vault.lessons(include_superseded=True)
    active = [l for l in lessons if not l.superseded_by]
    superseded = len(lessons) - len(active)
    lines.append(f"lessons: {len(active)} active" + (f" · {superseded} superseded" if superseded else ""))

    index_text = (
        vault.index_md.read_text(encoding="utf-8") if vault.index_md.is_file() else ""
    )
    missing = [l.lesson_id for l in active if l.lesson_id not in index_text]
    if missing:
        problems.append(f"index is stale ({len(missing)} lesson(s) missing) — run: agentbrain index")
        lines.append(f"index: STALE — {len(missing)} lesson(s) missing")
    else:
        lines.append("index: fresh")

    try:
        with vault.locked():
            pass
        lines.append("lock: acquire/release ok")
    except Exception as e:  # noqa: BLE001 — report, never crash
        problems.append(f"vault lock failed: {e}")
        lines.append(f"lock: FAILED — {e}")

    snap = Snapshot(vault.root).status()
    if snap.get("enabled"):
        last = snap.get("last_commit", "no commits yet")
        lines.append(f"snapshot: enabled · last: {last}")
        pending = snap.get("pending", 0)
        if pending:
            lines.append(
                f"  pending changes: {pending} file(s) — swept into the next commit, "
                "or run: agentbrain snapshot"
            )
    else:
        lines.append(
            "snapshot: disabled — install git and run: agentbrain init "
            f'"{vault.root}"'
        )

    entries = vault.log_entries()
    lines.append(f"log: {len(entries)} entries")

    if problems:
        lines.append("")
        lines.append(f"{len(problems)} issue(s) found:")
        lines += [f"- {p}" for p in problems]
    else:
        lines.append("")
        lines.append("Everything looks healthy.")

    lines += _mcp_hint(str(vault.root))
    return "\n".join(lines)
