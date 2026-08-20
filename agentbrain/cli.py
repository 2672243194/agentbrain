from __future__ import annotations

import argparse
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
    sub.add_parser("serve", help="Start the MCP server on stdio")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.cmd == "init":
        root = args.path or args.vault or Config.load().vault_dir
        print(scaffold.init(Path(root), force=args.force))
        return 0
    if args.cmd == "path":
        print(Config.load(args.vault).vault_dir)
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
        print(api.memory_query(query=args.query, top_k=args.top_k, mode="full" if args.full else "index", vault=vault))
    elif args.cmd == "ingest":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        print(api.memory_ingest(case_id=args.case, lesson=args.lesson, tags=tags, confidence=args.confidence, source_summary=args.summary, vault=vault))
    elif args.cmd == "lint":
        print(api.memory_lint(scope=args.scope, vault=vault))
    elif args.cmd == "distill":
        print(api.memory_distill(window_days=args.window_days, min_repeat=args.min_repeat, vault=vault))
    elif args.cmd == "index":
        vault.rebuild_index()
        print(f"Index rebuilt: {vault.relpath(vault.index_md)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
