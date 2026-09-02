from __future__ import annotations

import datetime as dt
from pathlib import Path

from .locking import atomic_write
from .snapshot import Snapshot
from .vault import Vault

_TEMPLATES = Path(__file__).parent / "templates"

_PROFILE_STUBS = {
    "Mutable-Hints": "Soft preferences the owner may revise over time. Agents are read-only here.",
    "_suggestions": "Agent-suggested profile changes awaiting owner approval. Agents may create files here.",
}

# Template files agents read at session start. Only these are managed by
# `agentbrain upgrade`; Index.md is generated, everything else is user content.
_UPDATABLE = ("AGENTS.md", "ONBOARDING.md")

# Template versions shipped by earlier releases. A vault file matching one of
# these is provably unmodified, so `upgrade` may replace it safely.
_LEGACY = {
    "AGENTS.md": (
        "legacy/AGENTS-0.4.1.md",
        "legacy/AGENTS-0.4.3.md",
        "legacy/AGENTS-0.4.6.md",
    ),
    "ONBOARDING.md": (),
}


def _tpl(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def _write(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def template_status(root: Path | str) -> dict[str, str]:
    """Per-file status for the updatable templates: current / legacy /
    custom / missing. 'custom' means the user edited it — never auto-replace."""
    root = Path(root).expanduser().resolve()
    out: dict[str, str] = {}
    for name in _UPDATABLE:
        p = root / name
        if not p.is_file():
            out[name] = "missing"
            continue
        content = p.read_text(encoding="utf-8-sig")
        if content == _tpl(name):
            out[name] = "current"
        elif any(content == _tpl(l) for l in _LEGACY.get(name, ())):
            out[name] = "legacy"
        else:
            out[name] = "custom"
    return out


def upgrade(root: Path | str) -> str:
    """Refresh shipped templates in an existing vault. Files that match a
    previously shipped template are updated in place; customized files are
    kept and reported so the owner can merge by hand. Never touches lessons,
    profiles, logs or the index."""
    root = Path(root).expanduser().resolve()
    v = Vault(root)
    if not v.root.is_dir():
        return f"No vault found at '{root}'. Run: agentbrain init \"{root}\""
    status = template_status(root)
    lines = [f"agentbrain upgrade: {root}", ""]
    changed = False
    with v.locked():
        for name in _UPDATABLE:
            s = status[name]
            if s == "current":
                lines.append(f"  [current] {name}")
            elif s == "missing":
                atomic_write(root / name, _tpl(name))
                lines.append(f"  [created] {name}")
                changed = True
            elif s == "legacy":
                atomic_write(root / name, _tpl(name))
                lines.append(f"  [updated] {name}")
                changed = True
            else:
                lines.append(
                    f"  [kept]    {name} — customized, merge the new template by hand "
                    f"(see templates/{name} in the agentbrain repo)"
                )
        if changed:
            v._snapshot_locked("upgrade: templates refreshed")
    lines += [
        "",
        "Then: pip install --upgrade mnemosyne-lite already got you the new code;",
        "restart your agent clients (MCP servers load code at process start), and",
        "refresh the discipline block in each project: agentbrain rules --agent <name> --write",
    ]
    return "\n".join(lines)


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
        (v.root / "ONBOARDING.md", _tpl("ONBOARDING.md")),
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
