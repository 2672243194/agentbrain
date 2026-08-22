# agentbrain

> Local-first long-term memory for AI agents — a plain Markdown vault + a thin MCP server.
> 给 AI Agent 用的本地长期记忆：纯 Markdown 知识库 + 薄 MCP server。

**三步上手 / Quick start (3 steps)**

```bash
pip install mnemosyne-lite             # Python >= 3.10（PyPI 包名；命令仍是 agentbrain）
agentbrain init ~/agentbrain  # 建立记忆库（幂等，可重复执行）
agentbrain doctor             # 自检：一切正常会显示 "Everything looks healthy."
```

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

把上面 JSON（vault 路径换成你的）粘进任意 MCP 客户端（Claude Code / Codex / Cursor / DSH / Open WebUI…），重启客户端，完成。Agent 从此有了跨会话、跨工具的长期记忆。

以后接入**新的** agent 不用你教：对它说一句「读 `AGENTS.md` 照做」即可——文件开头会把新来者引导到 `ONBOARDING.md`，它自己就能判断接入状态（已接 MCP / 只有 shell / 只能读文件）并完成配置或降级。

Paste that JSON (with your vault path) into any MCP client and restart it — done. Your agents now share one long-term memory.

[中文详细说明](#中文快速上手) · [English quickstart](#english-quickstart)

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
  `${ENV:VAR_NAME}` placeholders only, resolved at runtime via shell. Since 0.4.1 this
  is enforced, not just a rule: `memory_ingest` scans for credential-shaped content
  (sk-/ghp_/AKIA/xox-/AIza keys, bearer tokens, private-key blocks, `password=`
  assignments) and refuses the write, telling the agent to use a placeholder instead.
  Placeholders and teaching examples (`sk-xxx`, `YOUR_KEY`) ingest fine. `lint` also
  scans existing lessons and reports `SECRET` findings — read-only, never rewrites
  files. Hand-written files are never touched.

## Vault layout

```
agentbrain/                    # vault root (git-friendly, Obsidian-friendly)
├─ AGENTS.md                     # rules every agent reads at session start
├─ ONBOARDING.md                 # one-shot access setup for new agents
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
pip install mnemosyne-lite             # Python >= 3.10
agentbrain init ~/agentbrain           # 生成 vault 脚手架（幂等），自动开启 Git 快照
agentbrain doctor                      # 体检：vault/索引/锁/快照/log 一览
agentbrain ingest --case demo --lesson "部署前必须先跑迁移脚本" --tags 部署,运维
agentbrain query "部署 迁移"
agentbrain profile                     # 查看个人偏好（Immutable + Mutable-Hints）
agentbrain suggest --title "回复用中文" --change "偏好简洁的中文回复"    # 提交偏好建议
agentbrain lint                        # 体检：重复/过时/无标签/低置信度 → 生成整合提案
agentbrain apply lint-20260820-172206.md      # 人工审核后执行提案（自动归档）
agentbrain distill                     # 分析 log 中重复出现的模式 → 生成提升提案
agentbrain snapshot -m "手动备份"      # 手动提交快照（如用 Obsidian 手改文件后）
agentbrain rules --agent trae --write  # 把记忆纪律写进客户端规则文件（项目根目录运行）
```

> 说明：PyPI 包名为 `mnemosyne-lite`（`agentbrain` 在 PyPI 上与已有项目过于相似，无法注册）。
> 安装后的 CLI 命令与 Python 包名仍是 `agentbrain`，GitHub 仓库地址不变。

日常你只需要做三件事（频率都很低）：

| 事 | 命令 | 频率 |
|---|---|---|
| 想看库健不健康 | `agentbrain doctor` | 随意 |
| 记忆整理（清重复/过时） | `agentbrain lint` → 审核 → `agentbrain apply <提案>` | 约一周一次 |
| 手改文件后备份 | `agentbrain snapshot` | 改完就跑 |

其余全自动：Agent 会话开始读偏好、任务前查经验、学到东西写入（每次写入自动 git 快照，可回滚）。

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

注册 MCP 只让 agent **能**调记忆工具；要让它**每次会话主动**查库，再把纪律写进客户端的规则文件（在项目根目录运行，幂等可重复）：

```bash
agentbrain rules --agent claude --write   # 支持 claude / codex / trae / cursor
```

一条命令把「任务开始查库、中途遇到新问题再查、收尾存经验、密钥不入库」写进 `CLAUDE.md` / `AGENTS.md` / `.trae/rules/` / `.cursor/rules/`。

Onboarding a **new** agent later needs no instructions from you: just tell it
"read `AGENTS.md`" — the file routes first-timers to `ONBOARDING.md`, where they
detect their own access mode (MCP tools / shell / file-only) and wire themselves
up or fall back accordingly.

## English quickstart

```bash
pip install mnemosyne-lite             # Python >= 3.10
agentbrain init ~/agentbrain           # scaffold the vault (idempotent), enables git snapshots
agentbrain doctor                      # health check: vault, index, lock, snapshots, log
agentbrain ingest --case demo --lesson "Always run migrations before deploy" --tags deploy,ops
agentbrain query "deploy migrations"
agentbrain profile                     # print the owner profile
agentbrain suggest --title "Short replies" --change "Keep answers under 3 sentences."
agentbrain lint                        # health check → consolidation proposals
agentbrain apply lint-20260820-172206.md      # execute an approved proposal (archives it)
agentbrain distill                     # recurring-pattern analysis → promotion proposals
agentbrain snapshot -m "manual backup" # commit a snapshot (e.g. after hand-edits)
agentbrain rules --agent claude --write # install memory discipline into the client's rule file
agentbrain serve                       # start the MCP server on stdio
```

> Note: the PyPI distribution name is `mnemosyne-lite` (`agentbrain` was rejected
> as too similar to an existing PyPI project); the installed CLI command and the
> Python import name remain `agentbrain`.

Codex CLI (`~/.codex/config.toml`):

```toml
[mcp_servers.agentbrain]
command = "agentbrain"
args = ["serve"]
```

Registering MCP makes the tools *available*; making the client *actually query*
at task start takes one more line — write the discipline block into the
project's rule file (run in the project root, idempotent):

```bash
agentbrain rules --agent claude --write   # claude / codex / trae / cursor
```

It installs a short "agentbrain memory discipline" section into `CLAUDE.md`,
`AGENTS.md`, `.trae/rules/` or `.cursor/rules/`: query at task start, re-query
on new subtasks/errors, ingest at wrap-up with user confirmation, no secrets
ever.

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
  agents are serialized by an OS-level byte-range lock (`.vault.lock`, msvcrt/fcntl —
  released instantly if the holder crashes), and all file writes are atomic
  (temp + rename) so readers never see torn files.
- **Point-in-time recovery**: every vault is its own git repo (created by `init`,
  repo-local identity only). Each content write — ingest, apply, lint/distill
  proposal, suggestion, index rebuild — is auto-committed, so any bad edit can be
  rolled back with plain git. Query-driven `use_count` bumps ride along with the
  next content commit instead of polluting history. Works fully without git; if git
  is missing, snapshots are silently disabled.

## Changelog

- **0.4.3** — New `agentbrain rules` command: registers MCP and the tools become
  *available*, but clients only call them if a rule tells them to. One command
  now installs the memory discipline (query at task start, re-query on new
  subtasks/errors, ingest at wrap-up with confirmation, secrets never) into the
  client's own rule file — `--agent claude|codex|trae|cursor --write` writes
  `CLAUDE.md` / `AGENTS.md` / `.trae/rules/` / `.cursor/rules/` (Cursor gets an
  `alwaysApply` frontmatter block). Existing rule files are never overwritten —
  the block is appended; re-runs are no-ops via a marker. 95 tests.
- **0.4.2** — Self-service onboarding + hardening: new `ONBOARDING.md` in every
  vault routes first-time agents to the right access mode (MCP tools / shell /
  file-only) — onboarding a new agent is now just "read `AGENTS.md`";
  `memory_ingest` also scans `case_id` and `tags` for credentials (previously
  only lesson text and summary — a key smuggled into a filename or tag could
  slip past); hand-edited frontmatter with non-numeric `confidence`/`use_count`
  no longer breaks vault reads (per-field fallback to defaults). 87 tests.
- **0.4.1** — Enforced secret redaction: `memory_ingest` scans content and
  summaries for credential-shaped patterns (OpenAI/Anthropic/GitHub/AWS/Slack/Google
  tokens, Bearer headers, private-key blocks, `password=`/`api_key=` assignments) and
  refuses the write with a placeholder hint — the "secrets never enter the vault" rule
  is now a mechanism, not just AGENTS.md discipline. `${ENV:VAR}` references and
  teaching examples (`sk-xxx`) pass through. `lint` reports `SECRET` findings for
  pre-existing lessons (read-only). 84 tests.
- **0.4.0** — Maturity pass: git snapshots (every vault is a self-contained git repo;
  every content write is an auto-commit you can roll back — repo-local identity,
  graceful without git), `agentbrain doctor` one-shot health check (vault, index
  freshness, lock round-trip, snapshot status, log; prints a copy-paste MCP config
  with your vault path), `agentbrain snapshot` manual commit, fool-proof 3-step
  quickstart, PyPI-ready packaging. 74 tests.
- **0.3.2** — Locking rewrite + edge cases: the vault lock now uses OS-level
  byte-range locks (msvcrt on Windows, fcntl on POSIX) instead of
  create-file-and-reclaim — a crashed holder releases instantly (previously all
  writes failed for up to 60 s) and the stale-reclaim race (two waiters both
  unlinking and both acquiring) is gone. `agentbrain lint --scope tag:x` no longer
  reports false DANGLING for supersede targets outside the scope; `case_id`s
  containing glob metacharacters (`[`, `?`, `*`) no longer collide lesson ids;
  suggestion files use real YAML frontmatter (titles with colons/newlines used to
  corrupt it) and atomic writes. 65 tests.
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

## Roadmap — maintenance mode

The core promise — *a local, token-efficient, agent-shared long-term memory that
you own as plain Markdown* — is complete and battle-tested in daily use.
The project is now in maintenance mode: bug fixes, compatibility with new MCP
client versions, and small quality-of-life improvements. Big new subsystems are
deliberately out of scope; if a vault ever grows past a few hundred lessons,
these are the parked ideas:

- Hybrid fallback search (SQLite FTS5 + local embedding, RRF fusion)
- Keyring-backed `${ENV:...}` resolution helper

Done along the way:

- [x] Enforced secret redaction on ingest + SECRET findings in lint
- [x] Git snapshot on every write
- [x] `agentbrain apply <proposal>` to execute approved consolidations
- [x] Owner profile layer: `memory_profile` / `memory_suggest` + MCP resources
- [x] OS-level cross-process vault lock + atomic writes

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
