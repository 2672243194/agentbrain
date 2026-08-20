from __future__ import annotations

import re
from pathlib import Path

from .vault import Vault

_BLOCK_RE = re.compile(r"```agentbrain\s*\n(.*?)```", re.DOTALL)
_SUPERSEDE_RE = re.compile(r"^supersede:\s*(\S+)\s*->\s*(\S+)\s*$", re.MULTILINE)


class ProposalError(RuntimeError):
    pass


def parse_directives(text: str) -> list[tuple[str, str]]:
    directives: list[tuple[str, str]] = []
    for block in _BLOCK_RE.findall(text):
        directives.extend(_SUPERSEDE_RE.findall(block))
    return directives


def _resolve(vault: Vault, proposal: str | Path) -> Path:
    p = Path(proposal)
    if not p.is_absolute():
        for candidate in (vault.consolidations_dir / p, vault.root / p):
            if candidate.is_file():
                return candidate
    return p


def _would_cycle(vault: Vault, old: str, new: str) -> bool:
    seen: set[str] = set()
    cur = new
    while cur:
        if cur == old or cur in seen:
            return True
        seen.add(cur)
        lesson = vault.get(cur)
        cur = lesson.superseded_by if lesson else ""
    return False


def apply_proposal(vault: Vault, proposal: str | Path) -> str:
    p = _resolve(vault, proposal)
    if not p.is_file():
        raise ProposalError(
            f"Proposal not found: {proposal} "
            f"(looked in {vault.relpath(vault.consolidations_dir)} and vault root)"
        )
    if p.stem.endswith(".applied"):
        raise ProposalError(f"Proposal already applied: {vault.relpath(p)}")

    directives = parse_directives(p.read_text(encoding="utf-8"))
    if not directives:
        raise ProposalError(
            "No 'supersede' directives found in this proposal. "
            "Distill proposals are guidance for the owner; only lint merge proposals "
            "carry machine-applicable directives."
        )

    unique: list[tuple[str, str]] = []
    for d in directives:
        if d not in unique:
            unique.append(d)

    errors: list[str] = []
    for old, new in unique:
        if old == new:
            errors.append(f"{old} -> {new}: self-supersede refused")
            continue
        if vault.get(old) is None:
            errors.append(f"{old}: lesson not found")
            continue
        if vault.get(new) is None:
            errors.append(f"{new}: target lesson not found")
            continue
        if vault.get(old).superseded_by:
            errors.append(f"{old}: already superseded by {vault.get(old).superseded_by}")
            continue
        if _would_cycle(vault, old, new):
            errors.append(f"{old} -> {new}: would create a supersede cycle")
    if errors:
        raise ProposalError(
            "Refused — nothing applied:\n" + "\n".join(f"- {e}" for e in errors)
        )

    with vault.locked():  # validate + write as one transaction
        for old, new in unique:
            lesson = vault.get(old)
            if lesson is None or lesson.superseded_by:
                raise ProposalError(
                    f"Vault changed while applying ({old}); nothing was applied."
                )
            lesson.superseded_by = new
            vault._save_locked(lesson, rebuild=False)
        vault._rebuild_index_locked()
        renamed = p.with_name(p.stem + ".applied.md")
        p.rename(renamed)
        vault._append_log_locked("apply", f"{p.name} superseded:{len(unique)}")
    return "\n".join(
        [f"Applied {len(unique)} directive(s) from {vault.relpath(p)}:"]
        + [f"- {old} → {new} (superseded)" for old, new in unique]
        + ["", f"Proposal archived: {vault.relpath(renamed)}"]
    )
