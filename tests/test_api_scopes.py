"""Integration tests for per-client keys: scope enforcement and rate limiting."""
import pytest
from fastapi.testclient import TestClient

from repomind.api import create_app
from repomind.engine import Engine


def _write_config(tmp_path, body: str) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(body)
    return str(p)


@pytest.fixture
def scoped_client(tmp_path, base_config, monkeypatch):
    # No legacy admin token; only the three named keys below.
    monkeypatch.delenv("REPOMIND_API_TOKEN", raising=False)
    monkeypatch.setenv("READER_TOKEN", "r-tok")
    monkeypatch.setenv("WRITER_TOKEN", "w-tok")
    monkeypatch.setenv("ADMIN_TOKEN", "a-tok")
    cfg = _write_config(
        tmp_path,
        """
api:
  keys:
    - name: reader
      token_env: READER_TOKEN
      scopes: [read]
    - name: writer
      token_env: WRITER_TOKEN
      scopes: [write]
    - name: boss
      token_env: ADMIN_TOKEN
      scopes: [admin]
""".strip(),
    )
    monkeypatch.setenv("REPOMIND_CONFIG", cfg)
    return TestClient(create_app(engine=Engine(base_config)))


def test_reader_can_read_not_write(scoped_client):
    h = {"X-API-Key": "r-tok"}
    assert scoped_client.post("/ask", json={"question": "x"}, headers=h).status_code == 200
    assert scoped_client.get("/health", headers=h).status_code == 200
    # read key blocked from write + admin endpoints
    assert scoped_client.post("/sync", json={"scope": "all"}, headers=h).status_code == 403
    assert scoped_client.post("/forget", json={"target": "x"}, headers=h).status_code == 403


def test_writer_can_write_not_admin(scoped_client):
    h = {"X-API-Key": "w-tok"}
    assert scoped_client.post("/sync", json={"scope": "commits"}, headers=h).status_code == 200
    assert scoped_client.get("/health", headers=h).status_code == 200  # write implies read
    assert scoped_client.post("/forget", json={"target": "x"}, headers=h).status_code == 403


def test_admin_can_do_everything(scoped_client):
    h = {"X-API-Key": "a-tok"}
    assert scoped_client.post("/forget", json={"target": "x"}, headers=h).status_code == 200
    assert scoped_client.post("/sync", json={"scope": "commits"}, headers=h).status_code == 200
    assert scoped_client.get("/graph", headers=h).status_code == 200


def test_unknown_key_rejected(scoped_client):
    assert scoped_client.get("/health", headers={"X-API-Key": "nope"}).status_code == 401


def test_rate_limit_returns_429(tmp_path, base_config, monkeypatch):
    monkeypatch.delenv("REPOMIND_API_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_TOKEN", "a-tok")
    cfg = _write_config(
        tmp_path,
        """
api:
  rate_limit: 2
  rate_window: 1h
  keys:
    - name: boss
      token_env: ADMIN_TOKEN
      scopes: [admin]
""".strip(),
    )
    monkeypatch.setenv("REPOMIND_CONFIG", cfg)
    client = TestClient(create_app(engine=Engine(base_config)))
    h = {"X-API-Key": "a-tok"}
    assert client.get("/health", headers=h).status_code == 200
    assert client.get("/health", headers=h).status_code == 200
    r = client.get("/health", headers=h)  # 3rd within window -> limited
    assert r.status_code == 429
    assert "Retry-After" in r.headers
