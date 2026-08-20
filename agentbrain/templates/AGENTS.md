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

1. **Know the owner** — call `memory_profile` once per session (or read resource
   `agentbrain://profile`) and tailor language, tone and formatting accordingly.
2. **Task start** — call `memory_query` with the task topic (`top_k=5`).
   If MCP tools are unavailable, read `Case-Learnings/Index.md` and grep `Learnings/`.
3. **Before answering** — open the top 1–3 candidate lesson files in full.
4. **During the task** — NEVER edit or delete existing lessons. Create new ones only.
5. **When you learn something reusable** — call `memory_ingest` immediately.
   One lesson = one file = facts + applicable scenario + fix, ≤ 30 lines, no storytelling.
6. **Observed a preference?** — call `memory_suggest` with a short title and the
   proposed change. Never edit `Agent-Profile/` yourself; the owner reviews
   `_suggestions/` and decides.
7. **Session wrap-up** — when a substantive task ends, reflect once: what did this
   session teach that is worth remembering? Ingest each distinct lesson now
   (facts + scenario + fix, one file each) if not already ingested. Durable
   preference shift → `memory_suggest`. Then tell the owner in one line what you
   stored (or "nothing worth keeping"). Trivial sessions (small talk, quick
   lookups) need no wrap-up. Triggered by the owner saying e.g.
   "总结一下这次对话" / "wrap up", or proactively at natural task completion.
8. **Housekeeping (when the owner asks, or weekly)** — `memory_lint` writes proposals
   to `_consolidations/`. The owner merges content by hand and runs
   `agentbrain apply <file>`; never apply a proposal yourself.
9. **Recurring patterns** — `memory_distill` proposes promoting repeated patterns
   into a distilled lesson (human approval required).

## MCP resources (read-only context)

| URI | Content |
|-----|---------|
| `agentbrain://rules` | this file |
| `agentbrain://index` | `Case-Learnings/Index.md` |
| `agentbrain://profile` | merged owner profile |

## Hard rules

- **Secrets never enter the vault.** Never write passwords, tokens, API keys or
  private data into any file here. Reference them as `${ENV:VAR_NAME}` and resolve
  at runtime via shell. The vault is plain text and may be synced, shared or committed.
- **Append-only.** Existing lessons are immutable history. Corrections go into a new
  lesson or a `_consolidations/` proposal — never an in-place edit.
- **Token discipline.** Keep `source_summary` ≤ 60 chars; the index is the first
  retrieval layer and is read often.
