"""The web UI is served as static assets and is reachable without an API key
(it contains no data; all data calls from the browser still require a key)."""
from fastapi.testclient import TestClient

from repomind.api import create_app
from repomind.engine import Engine


def test_root_redirects_to_ui(base_config):
    client = TestClient(create_app(engine=Engine(base_config)))
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/ui/"


def test_ui_index_served(base_config):
    client = TestClient(create_app(engine=Engine(base_config)))
    r = client.get("/ui/")
    assert r.status_code == 200
    assert "RepoMind" in r.text
    assert "app.js" in r.text


def test_ui_assets_served(base_config):
    client = TestClient(create_app(engine=Engine(base_config)))
    assert client.get("/ui/styles.css").status_code == 200
    assert client.get("/ui/app.js").status_code == 200
