"""RepoMind: give a Git repository a brain.

A typed knowledge graph of commits, PRs, issues, people, decisions, and chat,
with hybrid recall powered by Cognee.
"""
from repomind.config import Config, load_config
from repomind.engine import Engine

__version__ = "0.1.0"
__all__ = ["Config", "Engine", "__version__", "load_config"]
