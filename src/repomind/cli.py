"""RepoMind CLI: backfill, ingest chat, sync, verify, ask, and serve.

Examples:
    repomind --config config.yaml backfill
    repomind --config config.yaml discord export.json
    repomind --config config.yaml sync --scope all --full
    repomind --config config.yaml verify
    repomind --config config.yaml ask "Who reviewed the auth PR?"
    repomind --config config.yaml stats
    repomind --config config.yaml serve
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from repomind.config import load_config
from repomind.engine import Engine


def _engine(args) -> Engine:
    config = load_config(args.config)
    return Engine(config)


def cmd_backfill(args) -> int:
    eng = _engine(args)
    g = eng.backfill_git()
    gh = eng.backfill_github()
    eng.improve()
    print(json.dumps({"git_docs": g, "github_docs": gh, "counts": eng.counts()}, indent=2))
    eng.close()
    return 0


def cmd_discord(args) -> int:
    eng = _engine(args)
    n = eng.ingest_discord(args.path)
    eng.improve()
    print(json.dumps({"messages": n, "counts": eng.counts()}, indent=2))
    eng.close()
    return 0


def cmd_sync(args) -> int:
    eng = _engine(args)
    mode = "full" if args.full else "incremental"
    report = eng.sync(scope=args.scope, mode=mode)
    print(json.dumps(report, indent=2))
    eng.close()
    return 0


def cmd_verify(args) -> int:
    eng = _engine(args)
    report = eng.verify(scope=args.scope)
    print(json.dumps(report, indent=2, default=str))
    eng.close()
    return 0 if report.get("consistent") else 1


def cmd_ask(args) -> int:
    eng = _engine(args)
    result = eng.query(args.question, limit=args.limit)
    print(result["answer"])
    print("\n--- traversal ---")
    for fact in result["facts"]:
        print(f"  - {fact}")
    eng.close()
    return 0


def cmd_stats(args) -> int:
    eng = _engine(args)
    print(json.dumps(eng.counts(), indent=2))
    eng.close()
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from repomind.auth import build_registry

    # The uvicorn factory (create_app) reads the config path from the
    # REPOMIND_CONFIG env var, so propagate --config to it here; otherwise the
    # served app would silently fall back to defaults (no API keys -> 503).
    if args.config:
        os.environ["REPOMIND_CONFIG"] = args.config

    # Warn loudly if no API keys are active: every protected endpoint fails
    # closed (503) until at least one key's secret is set in the environment.
    config = load_config(args.config)
    registry = build_registry(config)
    if registry.empty:
        print(
            "WARNING: no API keys configured. All protected endpoints will return "
            "503 until you set a key secret in the environment."
        )
    else:
        print(f"Active API keys: {', '.join(registry.names())}")
    uvicorn.run("repomind.api:create_app", factory=True, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="repomind", description="Give a Git repo a brain.")
    p.add_argument("--config", default=None, help="path to config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("backfill", help="ingest git history + GitHub PRs/issues").set_defaults(
        func=cmd_backfill
    )

    d = sub.add_parser("discord", help="ingest a Discord export JSON")
    d.add_argument("path")
    d.set_defaults(func=cmd_discord)

    s = sub.add_parser("sync", help="force a re-sync")
    s.add_argument("--scope", default="all", choices=["all", "prs", "issues", "commits"])
    s.add_argument("--full", action="store_true", help="full re-read + reconcile")
    s.set_defaults(func=cmd_sync)

    v = sub.add_parser("verify", help="verify graph vs source of truth")
    v.add_argument("--scope", default="all", choices=["all", "prs", "issues", "commits"])
    v.set_defaults(func=cmd_verify)

    a = sub.add_parser("ask", help="ask a question")
    a.add_argument("question")
    a.add_argument("--limit", type=int, default=5)
    a.set_defaults(func=cmd_ask)

    sub.add_parser("stats", help="show graph counts").set_defaults(func=cmd_stats)

    srv = sub.add_parser("serve", help="run the API server")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    srv.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
