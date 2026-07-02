"""Tests for the security model:
  - mandatory API key on every protected endpoint (401 missing, 503 fail-closed)
  - /livez is the only open endpoint
  - webhook fail-closed via HMAC (SEC-1) + 400 on malformed body (SEC-3)
"""
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from repomind.api import create_app
from repomind.engine import Engine
from tests.fakes import API_TOKEN, AUTH_HEADERS


def _app(base_config):
    # No default headers; each test controls auth explicitly.
    return TestClient(create_app(engine=Engine(base_config)))


# -- mandatory API key --------------------------------------------------------
def test_protected_endpoint_rejects_missing_key(base_config):
    client = _app(base_config)
    assert client.get("/health").status_code == 401
    assert client.get("/graph").status_code == 401
    assert client.post("/ask", json={"question": "x"}).status_code == 401
    assert client.post("/sync", json={"scope": "all"}).status_code == 401
    assert client.post("/forget", json={"target": "x"}).status_code == 401
    assert client.post("/ingest/message", json={"id": "1"}).status_code == 401


def test_protected_endpoint_rejects_wrong_key(base_config):
    client = _app(base_config)
    r = client.get("/health", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_protected_endpoint_accepts_x_api_key(base_config):
    client = _app(base_config)
    r = client.get("/health", headers={"X-API-Key": API_TOKEN})
    assert r.status_code == 200


def test_protected_endpoint_accepts_bearer(base_config):
    client = _app(base_config)
    r = client.get("/health", headers={"Authorization": f"Bearer {API_TOKEN}"})
    assert r.status_code == 200


def test_fail_closed_when_no_server_token(base_config, monkeypatch):
    # Even WITH a valid-looking client key, if the server has no token it refuses.
    monkeypatch.delenv("REPOMIND_API_TOKEN", raising=False)
    client = _app(base_config)
    r = client.get("/health", headers=AUTH_HEADERS)
    assert r.status_code == 503


def test_livez_is_open_and_leaks_nothing(base_config):
    client = _app(base_config)
    r = client.get("/livez")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}  # no counts / data


# -- SEC-1: webhook fail-closed (HMAC, exempt from API key) -------------------
def test_webhook_rejected_when_no_secret(base_config, monkeypatch):
    monkeypatch.delenv("REPOMIND_WEBHOOK_SECRET", raising=False)
    client = _app(base_config)
    r = client.post(
        "/webhook",
        content=json.dumps({"action": "opened", "issue": {"number": 1}}),
        headers={"X-GitHub-Event": "issues", "X-GitHub-Delivery": "d1"},
    )
    assert r.status_code == 401


def test_webhook_accepted_with_valid_signature(base_config, monkeypatch):
    secret = "s3cret"
    monkeypatch.setenv("REPOMIND_WEBHOOK_SECRET", secret)
    client = _app(base_config)
    body = json.dumps(
        {
            "action": "opened",
            "issue": {"number": 1, "title": "x", "body": "", "user": {"login": "ada"}},
            "repository": {"full_name": "demo/repo"},
        }
    ).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "d2",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200
    assert r.json()["ingested"] == 1


def test_webhook_rejects_bad_signature(base_config, monkeypatch):
    monkeypatch.setenv("REPOMIND_WEBHOOK_SECRET", "s3cret")
    client = _app(base_config)
    r = client.post(
        "/webhook",
        content=json.dumps({"action": "opened", "issue": {"number": 1}}),
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "d3",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert r.status_code == 401


# -- SEC-3: malformed JSON ----------------------------------------------------
def test_webhook_malformed_json_returns_400(base_config, monkeypatch):
    secret = "s3cret"
    monkeypatch.setenv("REPOMIND_WEBHOOK_SECRET", secret)
    client = _app(base_config)
    body = b"{not valid json"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "d4",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 400
