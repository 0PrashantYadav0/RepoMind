from repomind.config import load_config, parse_interval_seconds


def test_defaults_when_no_file():
    cfg = load_config(None)
    assert cfg.webhook.enabled is True
    assert cfg.polling.enabled is False  # OPTIONAL, off by default
    assert cfg.memory.backend == "memory"


def test_yaml_overrides(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        """
repo:
  name: demo/repo
  local_path: /tmp/x
memory:
  backend: cognee
  dataset: mybrain
polling:
  enabled: true
  interval: 30m
""".strip()
    )
    cfg = load_config(p)
    assert cfg.repo.name == "demo/repo"
    assert cfg.memory.backend == "cognee"
    assert cfg.memory.dataset == "mybrain"
    assert cfg.polling.enabled is True
    assert cfg.polling.interval == "30m"


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("REPOMIND_POLLING_ENABLED", "true")
    monkeypatch.setenv("REPOMIND_POLLING_INTERVAL", "5m")
    monkeypatch.setenv("REPOMIND_WEBHOOK_ENABLED", "false")
    cfg = load_config(None)
    assert cfg.polling.enabled is True
    assert cfg.polling.interval == "5m"
    assert cfg.webhook.enabled is False


def test_parse_interval():
    assert parse_interval_seconds("30s") == 30
    assert parse_interval_seconds("15m") == 900
    assert parse_interval_seconds("2h") == 7200
    assert parse_interval_seconds("1d") == 86400
    assert parse_interval_seconds("90") == 90
