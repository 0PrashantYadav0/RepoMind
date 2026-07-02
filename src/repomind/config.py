"""Configuration: YAML file + environment overrides. Nothing operational is
hard-coded. Secrets come from the environment only, never the file.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class IngestConfig(BaseModel):
    verify_after: bool = True
    batch_size: int = 50
    max_retries: int = 5
    retry_backoff: str = "exponential"
    max_commits: int = 0  # 0 = unlimited; cap git history walked per backfill/sync
    max_prs: int = 0      # 0 = unlimited; cap pull requests fetched from GitHub
    max_issues: int = 0   # 0 = unlimited; cap issues fetched from GitHub


class WebhookConfig(BaseModel):
    enabled: bool = True
    secret_env: str = "REPOMIND_WEBHOOK_SECRET"
    require_signature: bool = True  # fail-closed: reject unsigned webhooks


class PollingConfig(BaseModel):
    enabled: bool = False           # OPTIONAL, off by default
    interval: str = "15m"           # only used when enabled
    scope: list[str] = Field(default_factory=lambda: ["prs", "issues", "commits"])


class SyncConfig(BaseModel):
    default_mode: str = "incremental"  # "incremental" | "full"


class VerificationConfig(BaseModel):
    schedule: str = "0 3 * * *"


class RepoConfig(BaseModel):
    # "owner/name" for GitHub; local_path is the clone used by GitSource.
    name: str = ""
    local_path: str = ""
    github_token_env: str = "GITHUB_TOKEN"


class ApiKeyConfig(BaseModel):
    # A named client key. The secret is read from the env var named by token_env.
    name: str
    token_env: str
    scopes: list[str] = Field(default_factory=lambda: ["read"])


class ApiConfig(BaseModel):
    # Legacy single token (becomes an admin key named "default" if its env is set).
    token_env: str = "REPOMIND_API_TOKEN"  # noqa: S105 - env var NAME, not a secret
    # Per-client named keys with scopes.
    keys: list[ApiKeyConfig] = Field(default_factory=list)
    # Per-key rate limit: max `rate_limit` requests per `rate_window`. 0 disables.
    rate_limit: int = 0
    rate_window: str = "1m"


class MemoryConfig(BaseModel):
    # "memory" (in-memory, default/testing), "cognee" (in-process SDK adapter),
    # or "cognee_cloud" (hosted Cognee API -- just a key, nothing to self-host).
    backend: str = "memory"
    persist_path: str = ""           # optional JSON snapshot path for in-memory
    cognee_api_key_env: str = "COGNEE_API_KEY"
    dataset: str = "repomind"
    # --- Cognee Cloud (backend == "cognee_cloud"): hosted REST API. The URL is
    #     not a secret (config or COGNEE_SERVICE_URL); the key comes from env.
    service_url: str = ""             # e.g. "https://api.cognee.ai"
    service_url_env: str = "COGNEE_SERVICE_URL"
    cloud_search_type: str = "CHUNKS"  # seed retrieval type for the cloud search
    # Local / self-hosted Cognee tuning (applied only when backend == "cognee"
    # and the field is non-empty). Defaults below match a local Ollama setup.
    llm_provider: str = ""            # e.g. "ollama"
    llm_model: str = ""              # e.g. "llama3.2:3b"
    llm_endpoint: str = ""           # e.g. "http://localhost:11434/v1"
    embedding_provider: str = ""     # e.g. "ollama"
    embedding_model: str = ""        # e.g. "nomic-embed-text"
    embedding_endpoint: str = ""     # e.g. "http://localhost:11434/api/embed"
    embedding_dimensions: int = 0    # e.g. 768
    graph_provider: str = ""         # e.g. "kuzu" (embedded, local)
    huggingface_tokenizer: str = ""  # e.g. "bert-base-uncased"
    access_control: bool = True      # set False for local single-tenant kuzu


class StateConfig(BaseModel):
    db_path: str = "repomind_state.sqlite3"


class Config(BaseModel):
    repo: RepoConfig = Field(default_factory=RepoConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)

    def github_token(self) -> str | None:
        return os.environ.get(self.repo.github_token_env)

    def webhook_secret(self) -> str | None:
        return os.environ.get(self.webhook.secret_env)

    def cognee_api_key(self) -> str | None:
        return os.environ.get(self.memory.cognee_api_key_env)

    def cognee_service_url(self) -> str | None:
        return self.memory.service_url or os.environ.get(self.memory.service_url_env)


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load config from YAML if present, else defaults. Env vars override a few
    top-level toggles for ops convenience."""
    # Load secrets from a local .env if present. Real environment variables
    # always win (override=False), so CI/containers stay in control.
    load_dotenv(override=False)

    data: dict = {}
    if path:
        p = Path(path)
        if p.exists():
            data = yaml.safe_load(p.read_text()) or {}
    cfg = Config(**data)

    # Lightweight env overrides (handy in containers/CI).
    if (v := os.environ.get("REPOMIND_POLLING_ENABLED")) is not None:
        cfg.polling.enabled = v.lower() in {"1", "true", "yes"}
    if (v := os.environ.get("REPOMIND_POLLING_INTERVAL")) is not None:
        cfg.polling.interval = v
    if (v := os.environ.get("REPOMIND_WEBHOOK_ENABLED")) is not None:
        cfg.webhook.enabled = v.lower() in {"1", "true", "yes"}
    if (v := os.environ.get("REPOMIND_MEMORY_BACKEND")) is not None:
        cfg.memory.backend = v
    return cfg


def parse_interval_seconds(interval: str) -> int:
    """Parse '15m', '1h', '30s', '90' into seconds."""
    s = interval.strip().lower()
    if not s:
        raise ValueError("empty interval")
    if s[-1] in {"s", "m", "h", "d"}:
        unit = s[-1]
        num = float(s[:-1])
        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return int(num * mult)
    return int(float(s))
