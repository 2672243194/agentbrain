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
      "env": { "AGENTBRAIN_VAULT": "~/agentbrain" }
    }
  }
}
```

`AGENTBRAIN_VAULT` 可省略（默认 `~/agentbrain`）；vault 在别处时才需要写，路径按你的实际情况改。把上面 JSON 粘进任意 MCP 客户端（Claude Code / Codex / Cursor / DSH / Open WebUI…），重启客户端，完成。Agent 从此有了跨会话、跨工具的长期记忆。

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
agentbrain read demo-lesson-01         # 读取确认相关的记忆，并记录实际使用
agentbrain stats                       # 查看利用率统计
agentbrain profile                     # 查看个人偏好（Immutable + Mutable-Hints）
agentbrain suggest --title "回复用中文" --change "偏好简洁的中文回复"    # 提交偏好建议
agentbrain lint                        # 体检：重复/过时/无标签/低置信度 → 生成整合提案
agentbrain apply lint-20260820-172206.md      # 人工审核后执行提案（自动归档）
agentbrain verify my-case-lesson-01    # 重新确认某条经验仍然有效（消除 lint 的 STALE）
agentbrain distill                     # 分析 log 中重复出现的模式 → 生成提升提案
agentbrain snapshot -m "手动备份"      # 手动提交快照（如用 Obsidian 手改文件后）
agentbrain rules --agent trae --write  # 把记忆纪律写进客户端规则文件（项目根目录运行）
agentbrain rules --agent agentsmd --write  # agents.md 开放标准，覆盖 OpenCode/Gemini CLI 等
agentbrain rules --agent claude --write --global  # 写进用户级全局规则，所有项目生效
agentbrain install --agent codex --global         # Codex：MCP + 全局纪律一键接入
```

升级到新版本后（`pip install --upgrade mnemosyne-lite`）：

```bash
agentbrain upgrade                    # 刷新 vault 里的 AGENTS.md / ONBOARDING.md 模板
agentbrain rules --agent trae --write # 刷新各项目规则文件里的纪律块（旧版会原地更新）
# 然后重启你的 agent 客户端 —— MCP server 是进程启动时加载代码的
```

> 说明：PyPI 包名为 `mnemosyne-lite`（`agentbrain` 在 PyPI 上与已有项目过于相似，无法注册）。
> 安装后的 CLI 命令与 Python 包名仍是 `agentbrain`，GitHub 仓库地址不变。

日常你只需要做三件事（频率都很低）：

| 事 | 命令 | 频率 |
|---|---|---|
| 想看库健不健康 | `agentbrain doctor` | 随意 |
| 记忆整理（清重复/过时） | `agentbrain lint` → 审核 → `agentbrain apply <提案>` | 约一周一次 |
| 手改文件后备份 | `agentbrain snapshot` | 改完就跑 |

支持服务器 instructions 的客户端会获得默认引导：首次实质任务读偏好，任务前检索并选读相关经验，核对适用条件后使用；新经验须经过验证、查重并符合宿主授权规则后入库。客户端是否实际调用工具取决于其实现和规则，服务端不能保证自动执行。

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
      "env": { "AGENTBRAIN_VAULT": "~/agentbrain" }
    }
  }
}
```

`AGENTBRAIN_VAULT` 可省略（默认 `~/agentbrain`）；vault 在别处时才需要写。

Vault 路径解析顺序：`--vault` 参数 > `AGENTBRAIN_VAULT` 环境变量 > `~/agentbrain`。

注册 MCP 后，支持 instructions 的客户端可获得按需记忆工作流。对于忽略 instructions 的客户端，或需要显式配置工作流时，可把纪律写进客户端规则文件（在项目根目录运行，幂等可重复）：

```bash
agentbrain rules --agent claude --write   # 支持 claude / codex / trae / cursor / agentsmd（项目级）
agentbrain rules --agent agentsmd --write  # agents.md 开放标准：OpenCode、Gemini CLI、Amp 等都遵守
agentbrain rules --agent claude --write --global  # 用户级全局（~/.claude/CLAUDE.md），一次配置所有项目生效
```

该命令写入「任务前检索并选读、同主题复用、遇到未覆盖问题再查、经验证且授权后查重入库、密钥不入库」到 `CLAUDE.md` / `AGENTS.md` / `.trae/rules/` / `.cursor/rules/`。TRAE 和 Cursor 的全局规则在各自设置界面里，不走文件；claude / codex 支持 `--global`。

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
agentbrain verify my-case-lesson-01    # re-confirm a lesson is still valid (clears STALE)
agentbrain distill                     # recurring-pattern analysis → promotion proposals
agentbrain snapshot -m "manual backup" # commit a snapshot (e.g. after hand-edits)
agentbrain rules --agent claude --write # install memory discipline into the client's rule file
agentbrain serve                       # start the MCP server on stdio
```

After upgrading the package (`pip install --upgrade mnemosyne-lite`):

```bash
agentbrain upgrade                     # refresh AGENTS.md / ONBOARDING.md templates in the vault
agentbrain rules --agent claude --write # refresh the discipline block in project rule files
# then restart your agent clients — MCP servers load code at process start
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

Registering MCP also supplies server instructions to supporting clients.
Clients may ignore them; server configuration cannot guarantee tool calls.
For explicit client guidance, write the discipline block into the project's
rule file (run in the project root, idempotent):

```bash
agentbrain rules --agent codex --write           # per-project AGENTS.md
agentbrain rules --agent codex --write --global  # user-level ~/.codex/AGENTS.md
```

Or configure both MCP and the discipline block in one step:

```bash
agentbrain install --agent codex --global
```

It installs a short "agentbrain memory discipline" section into `CLAUDE.md`,
`AGENTS.md`, `.trae/rules/` or `.cursor/rules/`: query and selectively read before
work, check applicability, reuse previously read lessons, and re-query for
uncovered subtasks/errors. Ingest only verified, reusable findings after
duplicate checks and under host authorization rules; never store secrets.
The `agentsmd` target writes the agents.md open standard file,
followed by OpenCode, Gemini CLI, Amp and other standard-compliant tools.
TRAE and Cursor keep their global rules in their settings UIs;
claude and codex support `--global`.

## MCP tools

| Tool | Purpose |
|------|---------|
| `memory_query(query, top_k=5, mode="index", tag=None)` | Search lessons. `mode='index'` returns compact hits (id, summary, tags, path, gist); `mode='full'` adds full text; `tag` narrows results to one tag. |
| `memory_read(lesson_ids)` | Read up to 10 unique IDs and record full-text reads. Superseded IDs point to replacements; expired lessons are historical context and do not increase counts. |
| `memory_stats()` | Show active (not superseded, including expired), retired, read, unread and most-read lesson counts. Counts measure reads, not adoption or task success. |
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

Agents are expected to follow `AGENTS.md` in the vault root: read the profile once
for substantive work, query and selectively read before applying lessons, and
save verified findings after duplicate checks and under host authorization.
Never edit existing lessons or write secrets into the vault. Consolidation proposals carry
machine-readable directive blocks (```` ```agentbrain ````); only the owner
executes them via `agentbrain apply`.

## Design notes

- **Retrieval scoring**: BM25 over summary (×3), tags (×2), case id and body, with a
  CJK bigram tokenizer so Chinese queries work out of the box; results are boosted by
  `verified`, `use_count` and recent `last_verified_at`, demoted when stale (> 1 year).
- **Self-maintenance signals**: compact query hits do not increment `use_count`.
  Explicit `memory_read` and full-mode queries count non-expired, non-superseded
  reads once per ID per call; counts do not measure adoption or task success.
  `log.md` feeds `memory_distill` pattern analysis; `lint` refreshes nothing silently —
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
  is missing, snapshots are silently disabled. Individual file replacements are
  atomic; a disk failure can still interrupt a multi-file operation.

## Changelog

- **0.5.0** — Retrieval utilization + Codex onboarding round. Compact
  `memory_query` results no longer increment `use_count`; the new
  `memory_read` tool records actual full-text reads, preventing weak tail
  matches from reinforcing themselves in later ranking. New `memory_stats`
  reports active, retired, read, unread and most-read lessons. New
  `agentbrain install --agent codex --global` configures the MCP server,
  installs the memory discipline, runs a vault health check and prints the
  restart verification step. The shipped discipline now follows a two-stage
  query-then-read flow, with safe upgrade support for the 0.4.6 template.
  README Codex commands were corrected, and a mixed Chinese/English retrieval
  quality gate now enforces Recall@5 and MRR@5. 172 tests (+7).
- **0.4.6** — Robustness + scriptability round. Hand-written summaries are now
  normalized to one line and capped at ingest, and both the Index.md table and
  query output render them one-lined, so a multiline summary can no longer
  break the index. lint stops flagging retired lessons: ORPHAN/EXPIRED/
  LOWCONF skip superseded entries (SECRET/DANGLING still apply), ending
  recurring proposals that could never be acted on. The redaction scanner
  exempts lesson-id-shaped words (`…-lesson-01`, vault file names) so citing
  `pypi-…-lesson-01` no longer trips the PyPI-token pattern. `agentbrain
  snapshot` distinguishes committed / clean / failed instead of reporting
  every git failure as "nothing to commit". `lint` and `doctor` gained
  scripted exit codes (0 clean/healthy, 1 findings/issues, 2 bad scope /
  uninitialized vault). CLI output reconfigures to UTF-8 when piped, so
  emoji inside lesson text no longer crash redirects on Chinese-locale
  Windows. Query results are more token-frugal: three lines per hit (tags
  and path merged) and top_k clamped to 1–20; a new `tag` filter
  (`memory_query(tag=…)` / `agentbrain query --tag …`) narrows search to one
  tag. Index.md dropped its `used` column, so use-count bumps no longer
  rewrite the whole index. `agentbrain doctor` now reports broken lesson
  files (frontmatter present but unparseable) instead of letting them vanish
  silently, and lesson-id lookups reject path separators. `python -m
  agentbrain serve` works as a PATH-free MCP fallback (the doctor snippet
  shows both forms), lint findings carry explicit remedies, empty queries and
  unknown lint scopes are rejected with clear messages, tags past 8 are
  reported as dropped, oversize lessons (> 4000 chars) get a split hint, and
  nested locks across two vaults in one thread no longer deadlock.
  `agentbrain.__version__` is now the single version source (pyproject reads
  it dynamically), and a GitHub Actions matrix (ubuntu/windows × 3.10–3.12)
  runs the suite. 165 tests (+34).
- **0.4.5** — Signposting + standards round. Agents looking at the owner
  profile no longer miss the write channel: `memory_profile` output and the
  `agentbrain://profile` resource end with a note that the profile is
  read-only for agents and changes go through `memory_suggest`
  (`_suggestions/`, owner review), and the `memory_suggest` tool description
  states it is the only agent-writable path toward hard rules — closing the
  gap where an agent concluded "no interface exists" while the tool sat in
  its context. New `rules --agent agentsmd` target writes the agents.md
  open-standard file, so OpenCode, Gemini CLI, Amp and other
  standard-compliant clients get the discipline block with one command
  instead of per-client wiring. README MCP examples now use the portable
  default (`~/agentbrain`) and note that `AGENTBRAIN_VAULT` is optional.
  131 tests (+4).
- **0.4.4** — Autonomy + upgrade path + robustness round. Agents now ingest
  lessons autonomously and recall them without being told: MCP tool
  descriptions (always in the client's context once the server is registered)
  directly instruct when to query — task start, new subtask/error mid-task,
  before debugging — and to ingest the moment something is learned, with no
  user approval needed; the installed rule block and `AGENTS.md` say the same,
  and an empty `memory_query` result now suggests retrying with broader
  keywords or the other language before concluding nothing is stored.
  Upgrades no longer strand old versions in existing installs: new
  `agentbrain upgrade` refreshes vault templates (`AGENTS.md`,
  `ONBOARDING.md`) — files that match a previously shipped template are
  updated in place, customized ones are kept and reported; `agentbrain rules
  --write` now refreshes an outdated discipline block in place (marker-based,
  never touching surrounding user content), and `--global` writes the
  user-level rule file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`) so the
  discipline applies to every project instead of one; `doctor` reports
  outdated templates. New `agentbrain verify <id>` marks a lesson as re-verified today
  — the remedy for the STALE finding lint reports. `memory_ingest` warns when
  a near-duplicate active lesson exists (summary Jaccard ≥ 0.6), so repeated
  ingests surface immediately instead of waiting for the weekly lint.
  Redaction false positives fixed: 40-char git SHA-1 digests and Bearer-shaped
  English prose no longer trip the AWS-secret/Bearer patterns (real secrets
  still do). Lesson files saved with a UTF-8 BOM by Windows editors (Notepad)
  are now read correctly instead of silently vanishing from the index; the
  same BOM tolerance applies to profiles, logs, proposals and MCP resources.
  Long case ids are truncated (48 chars) instead of crashing with a
  path-too-long error; `verified: 'false'` in quoted frontmatter parses as
  false; lint now also scans tags and case ids for secrets (same scope as
  ingest); rule-file writes and git snapshot output decoding are hardened.
  127 tests.
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
