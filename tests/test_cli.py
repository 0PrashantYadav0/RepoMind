"""End-to-end CLI tests. Invoke `main(argv)` like a user would."""
from __future__ import annotations

import json

import pytest

from repomind.cli import main


@pytest.fixture
def cli_config(tmp_path, git_repo):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
repo:
  name: demo/repo
  local_path: {git_repo['path']}
memory:
  backend: memory
  persist_path: {tmp_path / 'graph.json'}
state:
  db_path: {tmp_path / 'state.sqlite3'}
""".strip()
    )
    return str(cfg)


def test_cli_backfill_then_stats(cli_config, capsys):
    assert main(["--config", cli_config, "backfill"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["git_docs"] == 5
    assert out["counts"]["by_type"]["Commit"] == 3

    assert main(["--config", cli_config, "stats"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["nodes"] >= 6


def test_cli_discord(cli_config, discord_export, capsys):
    main(["--config", cli_config, "backfill"])
    capsys.readouterr()
    assert main(["--config", cli_config, "discord", discord_export]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["messages"] == 2


def test_cli_ask(cli_config, capsys):
    main(["--config", cli_config, "backfill"])
    capsys.readouterr()
    assert main(["--config", cli_config, "ask", "who fixed the login bug"]) == 0
    out = capsys.readouterr().out
    assert "traversal" in out


def test_cli_sync_and_verify(cli_config, capsys):
    main(["--config", cli_config, "backfill"])
    capsys.readouterr()
    assert main(["--config", cli_config, "sync", "--scope", "commits", "--full"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "full"

    # The fixture's commits reference issues #7 and #12, which are NOT ingested
    # in commits-only scope (no GitHub token). verify must flag these as dangling
    # references -> consistent False -> exit code 1. This is the accuracy-first
    # behavior: dangling references are surfaced, not silently ignored.
    rc = main(["--config", cli_config, "verify", "--scope", "commits"])
    verify = json.loads(capsys.readouterr().out)
    assert verify["consistent"] is False
    assert len(verify["unresolved_references"]) >= 1
    assert rc == 1


def test_cli_requires_command(capsys):
    with pytest.raises(SystemExit):
        main([])
