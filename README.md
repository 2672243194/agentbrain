# agentbrain

> Local-first long-term memory for AI agents — a plain Markdown vault + a thin MCP server.
> 给 AI Agent 用的本地长期记忆：纯 Markdown 知识库 + 薄 MCP server。

[中文快速上手](#中文快速上手) · [English quickstart](#english-quickstart)

## Why agentbrain / 设计理念

- **Plain Markdown, no lock-in** — your memory is a folder of `.md` files. Open it in
  Obsidian, grep it, version it with Git. Remove agentbrain and the memory stays.
- **Token-efficient by design** — index-first retrieval: `Index.md` is the cheap first
  layer, BM25 (CJK-aware) only ranks candidates, and query output is compact by
  default (`mode='index'`); full text only on demand.
- **Append-only for agents** — agents may create lessons, never edit or delete them.
  Consolidation happens through proposals in `_consolidations/` that a human approves,
  which keeps multi-agent writes conflict-free.
- **Plug-and-play via MCP** — one server, every client: Claude Code, Codex CLI,
  OpenCode, Cursor, DSH, Open WebUI, ...
- **Secrets never enter the vault** — credentials live in env/keyring; lessons reference
  `${ENV:VAR_NAME}` placeholders only, resolved at runtime via shell.

## Vault layout

```
agentbrain/                    # vault root (git-friendly, Obsidian-friendly)
├─ AGENTS.md                     # rules every agent reads at session start
├─ Case-Learnings/
│  ├─ Index.md                   # auto-generated lesson index (retrieval layer 1)
│  ├─ log.md                     # append-only audit log
│  ├─ Learnings/                 # one lesson per file, YAML frontmatter
│  │  └─ case-001-lesson-01.md
│  └─ _consolidations/           # merge/promotion proposals (human approval)
└─ Agent-Profile/
   ├─ Immutable/                 # owner preferences & environment (agent read-only)
   ├─ Mutable-Hints/             # soft preferences (agent read-only)
   └─ _suggestions/              # agent-suggested profile changes
```

## 中文快速上手

```bash
pip install -e .                 # 需要 Python >= 3.10
agentbrain init ~/agentbrain     # 生成 vault 脚手架（幂等，可重复执行）
agentbrain ingest --case demo --lesson "部署前必须先跑迁移脚本" --tags 部署,运维
agentbrain query "部署 迁移"
agentbrain lint                    # 体检：重复/过时/无标签/低置信度 → 生成整合提案
agentbrain distill                 # 分析 log 中重复出现的模式 → 生成提升提案
```

在 MCP 客户端里接入（以 Claude Code 为例）：

```bash
claude mcp add agentbrain -- agentbrain serve
```

通用 MCP JSON 配置（Cursor / Open WebUI 等）：

```json
{
  "mcpServers": {
    "agentbrain": {
      "command": "agentbrain",
      "args": ["serve"],
      "env": { "AGENTBRAIN_VAULT": "D:\\agentbrain" }
    }
  }
}
```

Vault 路径解析顺序：`--vault` 参数 > `AGENTBRAIN_VAULT` 环境变量 > `~/agentbrain`。

## English quickstart

```bash
pip install -e .                 # Python >= 3.10
agentbrain init ~/agentbrain     # scaffold the vault (idempotent)
agentbrain ingest --case demo --lesson "Always run migrations before deploy" --tags deploy,ops
agentbrain query "deploy migrations"
agentbrain lint                    # health check → consolidation proposals
agentbrain distill                 # recurring-pattern analysis → promotion proposals
agentbrain serve                   # start the MCP server on stdio
```

Codex CLI (`~/.codex/config.toml`):

```toml
[mcp_servers.agentbrain]
command = "agentbrain"
args = ["serve"]
```

## MCP tools

| Tool | Purpose |
|------|---------|
| `memory_query(query, top_k=5, mode="index")` | Search lessons. `mode='index'` returns compact hits (id, summary, tags, path, gist); `mode='full'` adds full text. |
| `memory_ingest(case_id, lesson, tags, confidence=0.8, source_summary=None)` | Save a new lesson (facts + scenario + fix, ≤ 30 lines). Creates a file, updates Index.md and log.md. |
| `memory_lint(scope="all")` | Health check: duplicates, stale, expired, untagged, low-confidence. Writes a merge proposal to `_consolidations/`. |
| `memory_distill(window_days=30, min_repeat=3)` | Finds cases/tags ingested ≥ N times in the window and writes a promotion proposal. |

Agents are expected to follow `AGENTS.md` in the vault root: query at task start,
ingest on learnings, never edit existing lessons, never write secrets into the vault.

## Design notes

- **Retrieval scoring**: BM25 over summary (×3), tags (×2), case id and body, with a
  CJK bigram tokenizer so Chinese queries work out of the box; results are boosted by
  `verified`, `use_count` and recent `last_verified_at`, demoted when stale (> 1 year).
- **Self-maintenance signals**: every query hit increments `use_count`; `log.md`
  feeds `memory_distill` pattern analysis; `lint` refreshes nothing silently —
  every mutation of history goes through human-approved proposals.
- **Single-user, local-first**: no server daemon, no lock files; safe for one human
  driving several agents on one machine.

## Roadmap

- [ ] Hybrid fallback search (SQLite FTS5 + local embedding, RRF fusion) for large vaults
- [ ] `agentbrain apply <proposal>` to execute approved consolidations
- [ ] Temp-layer bridge (Mem0-style short-term memory → distill promotions)
- [ ] Keyring-backed `${ENV:...}` resolution helper
- [ ] Git snapshot hook on ingest/distill

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
