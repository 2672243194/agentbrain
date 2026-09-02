from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, api, scaffold
from .config import Config
from .vault import Vault, VaultNotInitialized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentbrain",
        description="Local-first long-term memory for AI agents (Markdown vault + MCP server).",
    )
    parser.add_argument("--vault", help="Vault directory (default: $AGENTBRAIN_VAULT or ~/agentbrain)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="Create/scaffold a memory vault")
    p.add_argument("path", nargs="?", help="Vault directory (default: --vault/$AGENTBRAIN_VAULT/~/agentbrain)")
    p.add_argument("--force", action="store_true", help="Overwrite template files that already exist")

    p = sub.add_parser("query", help="Search lessons")
    p.add_argument("query")
    p.add_argument("-k", "--top-k", type=int, default=5)
    p.add_argument("--full", action="store_true", help="Print full lesson text for top hits")
    p.add_argument("--tag", default=None, help="Only lessons carrying this tag")

    p = sub.add_parser("read", help="Read selected lessons in full and record actual use")
    p.add_argument("ids", nargs="+", help="Lesson id(s), up to 10")

    sub.add_parser("stats", help="Show vault utilization statistics")

    p = sub.add_parser("ingest", help="Save a new lesson")
    p.add_argument("--case", default="misc", help="Case id (default: misc)")
    p.add_argument("--lesson", required=True, help="Lesson text (facts + scenario + fix)")
    p.add_argument("--tags", default="", help="Comma-separated tags")
    p.add_argument("--confidence", type=float, default=0.8)
    p.add_argument("--summary", default=None, help="One-line summary (<= 60 chars); auto-derived if omitted")

    p = sub.add_parser("lint", help="Vault health check + consolidation proposal")
    p.add_argument("--scope", default="all", help='"all" or "tag:xxx"')

    p = sub.add_parser("distill", help="Recurring-pattern analysis + promotion proposal")
    p.add_argument("--window-days", type=int, default=30)
    p.add_argument("--min-repeat", type=int, default=3)

    sub.add_parser("index", help="Rebuild Case-Learnings/Index.md")
    sub.add_parser("path", help="Print resolved vault path")
    sub.add_parser("doctor", help="One-shot health check (vault, index, lock, snapshots)")
    sub.add_parser(
        "upgrade",
        help="Refresh shipped vault templates (AGENTS.md / ONBOARDING.md) to the current version",
    )

    p = sub.add_parser(
        "verify",
        help="Mark lesson(s) as re-verified today (updates last_verified_at; clears STALE lint findings)",
    )
    p.add_argument("ids", nargs="+", help="Lesson id(s), e.g. my-case-lesson-01")

    p = sub.add_parser(
        "rules",
        help="Print the agent-side memory discipline block, or write it into this project's rule file",
    )
    p.add_argument(
        "--agent",
        default="generic",
        help="claude | codex | trae | cursor | agentsmd | generic (default: generic, prints to stdout)",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Write the rule file into the current directory instead of printing",
    )
    p.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="Write to the user-level global rule file instead of the project "
        "(claude: ~/.claude/CLAUDE.md, codex: ~/.codex/AGENTS.md; applies to all projects)",
    )

    p = sub.add_parser("install", help="Configure an MCP client and install memory discipline")
    p.add_argument("--agent", required=True, choices=["codex"])
    p.add_argument("--global", dest="global_", action="store_true")

    p = sub.add_parser("snapshot", help="Commit all vault changes (e.g. after hand-editing files)")
    p.add_argument("-m", "--message", default="manual snapshot", help="Commit message")

    p = sub.add_parser("profile", help="Print the owner profile (Immutable + Mutable-Hints)")
    p = sub.add_parser("suggest", help="Propose a profile change (goes to Agent-Profile/_suggestions/)")
    p.add_argument("--title", required=True, help="Short title for the suggestion")
    p.add_argument("--change", required=True, help="What should change and why")

    p = sub.add_parser("apply", help="Execute an approved consolidation proposal")
    p.add_argument("proposal", help="Proposal file: bare name in _consolidations/, vault-relative or absolute path")

    sub.add_parser("serve", help="Start the MCP server on stdio")
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:  # real invocation; in-process calls (tests) keep their streams
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args(argv)

    if args.cmd == "init":
        root = args.path or args.vault or Config.load().vault_dir
        print(scaffold.init(Path(root), force=args.force))
        return 0
    if args.cmd == "path":
        print(Config.load(args.vault).vault_dir)
        return 0
    if args.cmd == "rules":
        from . import rules as rules_mod

        if args.write:
            if args.agent == "generic":
                print("Nothing to write for 'generic' — it prints the block only.", file=sys.stderr)
                return 2
            print(rules_mod.write(args.agent, Path.cwd(), global_=args.global_))
        else:
            print(rules_mod.render(args.agent))
        return 0
    if args.cmd == "install":
        from . import rules as rules_mod
        from .doctor import doctor

        try:
            install_vault = Vault.open(Config.load(args.vault))
        except VaultNotInitialized as e:
            print(str(e), file=sys.stderr)
            return 2
        vault_dir = install_vault.root
        codex = shutil.which("codex")
        if codex is None:
            print("Codex CLI not found on PATH.", file=sys.stderr)
            return 2
        existing = subprocess.run(
            [codex, "mcp", "get", "agentbrain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if existing.returncode == 0:
            mcp_status = "AgentBrain MCP already configured; existing entry kept."
        else:
            added = subprocess.run(
                [
                    codex,
                    "mcp",
                    "add",
                    "agentbrain",
                    "--env",
                    f"AGENTBRAIN_VAULT={vault_dir}",
                    "--",
                    sys.executable,
                    "-m",
                    "agentbrain",
                    "serve",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if added.returncode != 0:
                print(added.stderr.strip() or added.stdout.strip(), file=sys.stderr)
                return 2
            mcp_status = "AgentBrain MCP configured."
        rule_status = rules_mod.write("codex", Path.cwd(), global_=args.global_)
        print(
            f"{mcp_status}\n{rule_status}\n\n{doctor(install_vault)}\n\n"
            "Restart Codex, then call memory_profile to verify."
        )
        return 0
    if args.cmd == "doctor":
        from .doctor import doctor

        try:
            v = Vault.open(Config.load(args.vault))
        except VaultNotInitialized:
            print(doctor())
            return 2
        out = doctor(v)
        print(out)
        return 1 if "issue(s) found" in out else 0
    if args.cmd == "upgrade":
        cfg = Config.load(args.vault)
        print(scaffold.upgrade(Path(cfg.vault_dir)))
        return 0
    if args.cmd == "snapshot":
        from .snapshot import Snapshot

        try:
            v = Vault.open(Config.load(args.vault))
        except VaultNotInitialized as e:
            print(str(e), file=sys.stderr)
            return 2
        snap = Snapshot(v.root)
        if not snap.enabled and not snap.ensure():
            print("Snapshots unavailable: git not found.", file=sys.stderr)
            return 2
        with v.locked():
            status = snap.commit(args.message)
            if status == "committed":
                print(f"Snapshot committed: {args.message}")
            elif status == "clean":
                print("Nothing to commit — vault unchanged.")
            else:
                print(status, file=sys.stderr)
                return 2
        return 0
    if args.cmd == "serve":
        from . import mcp_server

        mcp_server.main()
        return 0

    try:
        vault = Vault.open(Config.load(args.vault))
    except VaultNotInitialized as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.cmd == "query":
        print(
            api.memory_query(
                query=args.query,
                top_k=args.top_k,
                mode="full" if args.full else "index",
                tag=args.tag,
                vault=vault,
            )
        )
    elif args.cmd == "read":
        print(api.memory_read(lesson_ids=args.ids, vault=vault))
    elif args.cmd == "stats":
        print(api.memory_stats(vault=vault))
    elif args.cmd == "ingest":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        print(api.memory_ingest(case_id=args.case, lesson=args.lesson, tags=tags, confidence=args.confidence, source_summary=args.summary, vault=vault))
    elif args.cmd == "lint":
        out = api.memory_lint(scope=args.scope, vault=vault)
        print(out)
        if out.startswith("Invalid scope"):
            return 2
        return 0 if out.startswith(("Lint clean", "No lessons in scope")) else 1
    elif args.cmd == "distill":
        print(api.memory_distill(window_days=args.window_days, min_repeat=args.min_repeat, vault=vault))
    elif args.cmd == "index":
        vault.rebuild_index()
        print(f"Index rebuilt: {vault.relpath(vault.index_md)}")
    elif args.cmd == "verify":
        verified, missing = vault.verify(args.ids)
        if verified:
            print(f"Verified {len(verified)} lesson(s): {', '.join(verified)}")
        if missing:
            print(f"Not found: {', '.join(missing)}", file=sys.stderr)
            return 1 if verified else 2
    elif args.cmd == "profile":
        print(api.memory_profile(vault=vault))
    elif args.cmd == "suggest":
        print(api.memory_suggest(title=args.title, change=args.change, vault=vault))
    elif args.cmd == "apply":
        from .apply import ProposalError, apply_proposal

        try:
            print(apply_proposal(vault, args.proposal))
        except ProposalError as e:
            print(str(e), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
