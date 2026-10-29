# AGENTS.md — How to use this memory vault

> New to this vault? Read `ONBOARDING.md` first to get your access working,
> then come back here.

You (the AI agent) share this vault across all sessions and tools (Claude Code,
Codex, OpenCode, Cursor, ...). Use this workflow for substantive tasks.

## Vault layout

| Path | Meaning | Your access |
|------|---------|-------------|
| `Case-Learnings/Index.md` | Lesson catalog for file-only access; MCP searches selectively | read |
| `Case-Learnings/Learnings/*.md` | One lesson per file | read, create |
| `Case-Learnings/log.md` | Append-only audit log | maintained by tools |
| `Case-Learnings/_consolidations/` | Merge / promotion proposals | create, read |
| `Agent-Profile/Immutable/` | Owner's preferences & environment | READ-ONLY |
| `Agent-Profile/Mutable-Hints/` | Soft preferences the owner may revise | READ-ONLY |
| `Agent-Profile/_suggestions/` | Your suggested profile changes | create |

## Session workflow

- Follow host authorization rules for memory reads and writes; existing
  authorization remains valid.
- At the first substantive task in a conversation session, call `memory_profile`
  once, not once per MCP connection. Skip mechanical memory calls for small talk
  or repeated questions.
- Before substantive work, use `memory_query` (top_k=5) with concrete task/error keywords. When relevant
  candidates exist, use `memory_read` for 1-3 ids not yet read this session;
  search hits are candidates, not full lessons.
- Apply lessons only after checking task preconditions, environment and
  time-sensitive assumptions against current evidence.
- Reuse already-read lessons on the same topic. Query again for a new error or
  subtask only when earlier results do not cover it. No match? Retry once with
  broader keywords or the other language.
- Save verified, reusable new findings when authorized. Before `memory_ingest`, check duplicates
  with `memory_query` (reuse relevant prior results), then read suspected matches
  not yet read. Avoid duplicate lessons. One lesson = scenario, evidence and fix,
  <= 30 lines. Never store guesses, transcripts, secrets, tokens or passwords;
  reference secrets as `${ENV:VAR_NAME}`.
- Personal preferences go only through `memory_suggest`; Immutable is read-only.

If MCP tools are unavailable, read `Case-Learnings/Index.md` and select relevant
lesson files in `Learnings/`. Reuse files already read on the same topic.
Do not hand-write lessons; use MCP/CLI when available or tell the owner what
could be saved. Existing lessons and profiles remain read-only to agents.

**Housekeeping only when the owner asks** — `memory_lint` and `memory_distill`
write proposals to `_consolidations/`. The owner reviews and merges the proposal,
then runs `agentbrain apply <file>`; never apply a proposal yourself.

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
- **Token discipline.** Keep `source_summary` ≤ 60 chars. Use compact search
  results and selected reads; MCP access does not require loading the whole index.
