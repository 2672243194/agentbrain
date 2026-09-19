from __future__ import annotations

import re
from pathlib import Path

from .locking import atomic_write
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


def _find_cycle(graph: dict[str, str]) -> list[str]:
    """Check each replacement chain once, without recursive traversal."""
    checked: set[str] = set()
    for start in graph:
        trail: dict[str, int] = {}
        current = start
        while current and current not in checked:
            if current in trail:
                return list(trail)[trail[current]:] + [current]
            trail[current] = len(trail)
            current = graph.get(current, "")
        checked.update(trail)
    return []


def _missing_target(graph: dict[str, str], starts: dict[str, str]) -> str:
    """Require proposed replacements to lead to existing lessons."""
    checked: set[str] = set()
    for start in starts:
        current = start
        while current and current not in checked:
            if current not in graph:
                return current
            checked.add(current)
            current = graph[current]
    return ""


def apply_proposal(vault: Vault, proposal: str | Path) -> str:
    with vault.locked():
        p = _resolve(vault, proposal)
        if not p.is_file():
            raise ProposalError(
                f"Proposal not found: {proposal} "
                f"(looked in {vault.relpath(vault.consolidations_dir)} and vault root)"
            )
        if p.stem.endswith(".applied"):
            raise ProposalError(f"Proposal already applied: {vault.relpath(p)}")
        renamed = p.with_name(p.stem + ".applied.md")
        if renamed.exists():
            raise ProposalError(
                f"Refused — nothing applied: proposal archive already exists: "
                f"{vault.relpath(renamed)}"
            )

        directives = parse_directives(p.read_text(encoding="utf-8-sig"))
        if not directives:
            raise ProposalError(
                "No 'supersede' directives found in this proposal. "
                "Distill proposals are guidance for the owner; only lint merge proposals "
                "carry machine-applicable directives."
            )
        unique = list(dict.fromkeys(directives))
        lessons = {l.lesson_id: l for l in vault.lessons(include_superseded=True)}
        graph = {key: lesson.superseded_by for key, lesson in lessons.items()}
        targets: dict[str, str] = {}
        errors: list[str] = []
        for old, new in unique:
            if old in targets and targets[old] != new:
                errors.append(f"{old}: conflicting targets {targets[old]} and {new}")
                continue
            targets[old] = new
            if old == new:
                errors.append(f"{old} -> {new}: self-supersede refused")
            elif old not in lessons:
                errors.append(f"{old}: lesson not found")
            elif new not in lessons:
                errors.append(f"{new}: target lesson not found")
            elif lessons[old].superseded_by:
                errors.append(
                    f"{old}: already superseded by {lessons[old].superseded_by}"
                )
            else:
                graph[old] = new
        if not errors:
            cycle = _find_cycle(graph)
            if cycle:
                errors.append("final supersede graph contains a cycle: " + " -> ".join(cycle))
            missing = _missing_target(graph, targets)
            if missing:
                errors.append(f"replacement chain reaches missing target lesson: {missing}")
        if errors:
            raise ProposalError(
                "Refused — nothing applied:\n" + "\n".join(f"- {e}" for e in errors)
            )

        try:
            prepared = [
                vault._prepare_metadata_update(old, {"superseded_by": new})
                for old, new in unique
            ]
        except ValueError as error:
            raise ProposalError(f"Refused — nothing applied: {error}") from error
        for lesson, text in prepared:
            atomic_write(lesson.path, text, newline="")
        vault._rebuild_index_locked()
        p.rename(renamed)
        vault._append_log_locked("apply", f"{p.name} superseded:{len(unique)}")
        vault._snapshot_locked(f"apply: {p.name} (superseded {len(unique)})")
    return "\n".join(
        [f"Applied {len(unique)} directive(s) from {vault.relpath(p)}:"]
        + [f"- {old} → {new} (superseded)" for old, new in unique]
        + ["", f"Proposal archived: {vault.relpath(renamed)}"]
    )
