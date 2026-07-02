import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from repomind.api import create_app
from repomind.engine import Engine
from tests.fakes import AUTH_HEADERS


def make_client(base_config, fake_github_repo):
    eng = Engine(base_config)
    eng.set_github_source(fake_github_repo)
    eng.backfill_git()
    eng.backfill_github()
    app = create_app(engine=eng)
    return TestClient(app, headers=AUTH_HEADERS), eng


def test_health_and_graph(base_config, fake_github_repo):
    client, _ = make_client(base_config, fake_github_repo)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    g = client.get("/graph").json()
    assert g["nodes"] and g["edges"]
    assert any(n["type"] == "PullRequest" for n in g["nodes"])


def test_ask_endpoint(base_config, fake_github_repo):
    client, _ = make_client(base_config, fake_github_repo)
    r = client.post("/ask", json={"question": "login bug"})
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body and "subgraph" in body


def test_webhook_endpoint_ingests_live(base_config, fake_github_repo, monkeypatch):
    secret = "s3cret"
    monkeypatch.setenv("REPOMIND_WEBHOOK_SECRET", secret)
    client, eng = make_client(base_config, fake_github_repo)
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 500,
            "title": "Live PR",
            "body": "Fixes #7",
            "user": {"login": "ada"},
            "state": "open",
        },
        "repository": {"full_name": "demo/repo"},
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "guid-live-1",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200
    assert r.json()["ingested"] == 1
    # The new node is queryable immediately (the always-up-to-date claim).
    g = client.get("/graph").json()
    assert any(n["id"].endswith(":500") for n in g["nodes"])


def test_sync_and_verify_endpoints(base_config, fake_github_repo):
    client, _ = make_client(base_config, fake_github_repo)
    s = client.post("/sync", json={"scope": "all", "mode": "incremental"})
    assert s.status_code == 200
    v = client.post("/verify", json={"scope": "all"})
    assert v.status_code == 200
    assert v.json()["consistent"] is True
