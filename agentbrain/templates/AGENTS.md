# AGENTS.md — How to use this memory vault

You (the AI agent) share this vault across all sessions and tools (Claude Code,
Codex, OpenCode, Cursor, ...). Read this file at session start. It is small on purpose.

## Vault layout

| Path | Meaning | Your access |
|------|---------|-------------|
| `Case-Learnings/Index.md` | Index of all lessons — read this FIRST | read |
| `Case-Learnings/Learnings/*.md` | One lesson per file | read, create |
| `Case-Learnings/log.md` | Append-only audit log | maintained by tools |
| `Case-Learnings/_consolidations/` | Merge / promotion proposals | create, read |
| `Agent-Profile/Immutable/` | Owner's preferences & environment | READ-ONLY |
| `Agent-Profile/Mutable-Hints/` | Soft preferences the owner may revise | READ-ONLY |
| `Agent-Profile/_suggestions/` | Your suggested profile changes | create |

## Session workflow

1. **Task start** — call `memory_query` with the task topic (`top_k=5`).
   If MCP tools are unavailable, read `Case-Learnings/Index.md` and grep `Learnings/`.
2. **Before answering** — open the top 1–3 candidate lesson files in full.
3. **During the task** — NEVER edit or delete existing lessons. Create new ones only.
4. **When you learn something reusable** — call `memory_ingest` immediately.
   One lesson = one file = facts + applicable scenario + fix, ≤ 30 lines, no storytelling.
5. **Housekeeping (when the owner asks, or weekly)** — `memory_lint` writes proposals
   to `_consolidations/`. A human approves them; never apply a proposal yourself.
6. **Recurring patterns** — `memory_distill` proposes promoting repeated patterns
   into a distilled lesson (human approval required).

## Hard rules

- **Secrets never enter the vault.** Never write passwords, tokens, API keys or
  private data into any file here. Reference them as `${ENV:VAR_NAME}` and resolve
  at runtime via shell. The vault is plain text and may be synced, shared or committed.
- **Append-only.** Existing lessons are immutable history. Corrections go into a new
  lesson or a `_consolidations/` proposal — never an in-place edit.
- **Token discipline.** Keep `source_summary` ≤ 60 chars; the index is the first
  retrieval layer and is read often.
