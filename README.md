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
│  │  └─ case-001-lesson-01.md   # 文件名 = {case_id}-lesson-{NN}，自动生成
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
agentbrain profile                # 查看个人偏好（Immutable + Mutable-Hints）
agentbrain suggest --title "回复用中文" --change "偏好简洁的中文回复"   # 提交偏好建议
agentbrain lint                    # 体检：重复/过时/无标签/低置信度 → 生成整合提案
agentbrain apply lint-20260820-172206.md   # 人工审核后执行提案（自动归档）
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
agentbrain profile                # print the owner profile
agentbrain suggest --title "Short replies" --change "Keep answers under 3 sentences."
agentbrain lint                    # health check → consolidation proposals
agentbrain apply lint-20260820-172206.md   # execute an approved proposal (archives it)
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
| `memory_profile()` | Returns the owner profile (hard rules + soft preferences). Read-only; agents call it once per session to tailor behavior. |
| `memory_suggest(title, change)` | Proposes a profile change into `Agent-Profile/_suggestions/` for the owner to review — agents never edit the profile itself. |

## MCP resources

| URI | Content |
|-----|---------|
| `agentbrain://rules` | `AGENTS.md` — vault rules for every agent |
| `agentbrain://index` | `Case-Learnings/Index.md` — retrieval layer 1 |
| `agentbrain://profile` | merged owner profile (read-only) |

Agents are expected to follow `AGENTS.md` in the vault root: read the profile at
session start, query at task start, ingest on learnings, never edit existing
lessons, never write secrets into the vault. Consolidation proposals carry
machine-readable directive blocks (```` ```agentbrain ````); only the owner
executes them via `agentbrain apply`.

## Design notes

- **Retrieval scoring**: BM25 over summary (×3), tags (×2), case id and body, with a
  CJK bigram tokenizer so Chinese queries work out of the box; results are boosted by
  `verified`, `use_count` and recent `last_verified_at`, demoted when stale (> 1 year).
- **Self-maintenance signals**: every query hit increments `use_count`; `log.md`
  feeds `memory_distill` pattern analysis; `lint` refreshes nothing silently —
  every mutation of history goes through human-approved proposals.
- **Single-user, local-first**: no daemon, no ports; concurrent writes from several
  agents are serialized by a transient `.vault.lock` (auto-cleaned, stale-reclaimed
  after 60 s), and all file writes are atomic (temp + rename) so readers never see
  torn files.

## Changelog

- **0.3.1** — Data-integrity fixes: concurrent same-case ingests no longer overwrite
  each other (lesson-id allocation moved inside the vault lock); `confidence: 0.0`
  round-trips correctly (was silently coerced to 0.8); lint/distill proposals are
  written atomically under the lock with collision-free names; merge proposals now
  keep the more-used lesson as the keeper; duplicate detection pre-tokenizes (O(n²)
  without re-tokenizing per pair). Session wrap-up rule added to AGENTS.md. 59 tests.
- **0.3.0** — Concurrency & robustness: cross-process/thread vault write lock
  (`.vault.lock`, re-entrant, stale-reclaim), atomic writes (temp + rename),
  `apply` is now a single transaction; query no longer rebuilds the index once per
  hit (one rebuild per query); stray non-lesson `.md` files in `Learnings/` are
  ignored; `confidence` clamped to [0,1]; unknown `mode` falls back to `index`;
  same-second suggestions no longer overwrite each other. 54 tests.
- **0.2.0** — Owner profile layer (`memory_profile` / `memory_suggest` + MCP
  resources), lint/distill proposals with machine-readable directive blocks,
  `agentbrain apply` with cycle/self-supersede/dangling checks.
- **0.1.0** — Initial MVP: vault + frontmatter + CJK-aware BM25 retrieval,
  MCP server (query/ingest/lint/distill) + CLI, scaffold templates.

## Roadmap

- [ ] Hybrid fallback search (SQLite FTS5 + local embedding, RRF fusion) for large vaults
- [x] `agentbrain apply <proposal>` to execute approved consolidations
- [x] Owner profile layer: `memory_profile` / `memory_suggest` + MCP resources
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
