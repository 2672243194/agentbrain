# ONBOARDING.md — first time in this vault? Read me once, then move on

You were pointed here because this is your first session with this vault. This
file is one-shot guidance: it tells you how to get access working, then you
never need it again. The real rules live in `AGENTS.md`.

## Step 1 — Which state are you in?

Check what you can do, in this order:

1. **You have `memory_*` tools** (memory_query, memory_ingest, ...) — MCP is
   already wired up. Skip to "You're done".
2. **Shell access only** — you can register the MCP server yourself; see below.
3. **File access only** — work in file mode; see below.

## Shell access: register the MCP server (recommended)

Add this server to your own client's MCP configuration:

- server name: `agentbrain`
- command: `agentbrain` (fallback full path if the command is not on PATH)
- args: `["serve"]`
- env: `AGENTBRAIN_VAULT` = the absolute path of this vault folder

Do not modify any other servers already configured there. After registering,
the owner must restart you for the tools to appear. If you cannot register,
fall back to file mode and tell the owner.

**Verify after restart:** call `memory_profile` once — if it returns the owner's
profile, you are connected.

**Make the discipline stick:** having tools does not guarantee a client calls
them at task start. Suggest the owner run
`agentbrain rules --agent <claude|codex|trae|cursor> --write` in the project
root — it installs a short rules block so every future session in that project
queries the vault automatically.

## File access only: how to work without MCP

- `Case-Learnings/Index.md` is the catalog — read it first, grep
  `Case-Learnings/Learnings/` for full text of promising entries.
- `Agent-Profile/` holds the owner's preferences — read, never edit.
- **Do not hand-write lesson files**: lesson ids, the index and the audit log
  must stay consistent. When you learn something worth keeping, tell the owner
  (or ingest via MCP/CLI once available) instead of creating files yourself.
- Never write secrets into any file in this vault.

## You're done

Whatever your access mode, the session workflow, hard rules and vault layout
are in `AGENTS.md` — read that next. You will not need this file again.
