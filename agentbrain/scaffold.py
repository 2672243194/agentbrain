from __future__ import annotations

import datetime as dt
from pathlib import Path

from .snapshot import Snapshot
from .vault import Vault

_TEMPLATES = Path(__file__).parent / "templates"

_PROFILE_STUBS = {
    "Mutable-Hints": "Soft preferences the owner may revise over time. Agents are read-only here.",
    "_suggestions": "Agent-suggested profile changes awaiting owner approval. Agents may create files here.",
}


def _tpl(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def _write(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def init(root: Path | str, force: bool = False) -> str:
    root = Path(root).expanduser().resolve()
    v = Vault(root)
    v.learnings_dir.mkdir(parents=True, exist_ok=True)
    v.consolidations_dir.mkdir(parents=True, exist_ok=True)
    immutable = v.root / "Agent-Profile" / "Immutable"
    immutable.mkdir(parents=True, exist_ok=True)
    for name, note in _PROFILE_STUBS.items():
        d = v.root / "Agent-Profile" / name
        d.mkdir(parents=True, exist_ok=True)
        _write(d / "README.md", f"# {name}\n\n{note}\n", force)

    today = dt.date.today().isoformat()
    demo = v.learnings_dir / "case-demo-lesson-01.md"
    files = [
        (v.root / "AGENTS.md", _tpl("AGENTS.md")),
        (v.index_md, _tpl("Index.md")),
        (v.log_md, _tpl("log.md")),
        (immutable / "profile.md", _tpl("profile.md")),
        (demo, _tpl("lesson-demo.md").replace("{{DATE}}", today)),
    ]

    lines = [f"agentbrain vault ready: {root}", ""]
    for path, content in files:
        wrote = _write(path, content, force)
        lines.append(f"  [{'created' if wrote else 'kept   '}] {v.relpath(path)}")

    v.rebuild_index()
    if not v.log_md.read_text(encoding="utf-8").strip().endswith(f"[{today}] init | vault"):
        v.append_log("init", "vault")
    if Snapshot(root).ensure():
        with v.locked():
            v._snapshot_locked("init: vault scaffolded")
        lines += ["", "Snapshots: enabled — every write is a git commit you can roll back."]
    else:
        lines += [
            "",
            "Snapshots: disabled (git not found). Everything works without it;",
            "install git to enable point-in-time recovery.",
        ]
    lines += [
        "",
        "Next:",
        "  agentbrain ingest --case my-case --lesson '...' --tags a,b",
        "  agentbrain query 'topic'",
        "  agentbrain lint / agentbrain distill",
        "  agentbrain serve   # MCP server over stdio",
    ]
    return "\n".join(lines)
