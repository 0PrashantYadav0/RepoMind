"""Unit tests for the auth module: scope hierarchy, key registry, rate limiter."""
from repomind.auth import (
    ApiKey,
    KeyRegistry,
    RateLimiter,
    build_registry,
    has_scope,
)


# -- scope hierarchy ----------------------------------------------------------
def test_scope_hierarchy():
    admin = ApiKey("a", "t", ("admin",))
    writer = ApiKey("w", "t", ("write",))
    reader = ApiKey("r", "t", ("read",))

    # admin implies everything
    assert has_scope(admin, "read") and has_scope(admin, "write") and has_scope(admin, "admin")
    # write implies read, but not admin
    assert has_scope(writer, "read") and has_scope(writer, "write")
    assert not has_scope(writer, "admin")
    # read implies only read
    assert has_scope(reader, "read")
    assert not has_scope(reader, "write") and not has_scope(reader, "admin")


# -- registry matching --------------------------------------------------------
def test_registry_match_and_empty():
    reg = KeyRegistry([ApiKey("a", "secret-a", ("read",))])
    assert not reg.empty
    assert reg.match("secret-a").name == "a"
    assert reg.match("wrong") is None
    assert reg.match(None) is None
    assert KeyRegistry([]).empty


def test_build_registry_legacy_token(monkeypatch):
    monkeypatch.setenv("REPOMIND_API_TOKEN", "legacy")
    from repomind.config import Config

    reg = build_registry(Config())
    key = reg.match("legacy")
    assert key.name == "default" and "admin" in key.scopes


def test_build_registry_named_keys(monkeypatch):
    monkeypatch.delenv("REPOMIND_API_TOKEN", raising=False)
    monkeypatch.setenv("READER_TOKEN", "r-tok")
    monkeypatch.setenv("WRITER_TOKEN", "w-tok")
    from repomind.config import ApiConfig, ApiKeyConfig, Config

    cfg = Config(
        api=ApiConfig(
            keys=[
                ApiKeyConfig(name="reader", token_env="READER_TOKEN", scopes=["read"]),
                ApiKeyConfig(name="writer", token_env="WRITER_TOKEN", scopes=["write"]),
                ApiKeyConfig(name="ghost", token_env="UNSET_TOKEN", scopes=["admin"]),
            ]
        )
    )
    reg = build_registry(cfg)
    assert set(reg.names()) == {"reader", "writer"}  # ghost skipped (no secret)
    assert reg.match("r-tok").scopes == ("read",)
    assert reg.match("w-tok").scopes == ("write",)


# -- rate limiter -------------------------------------------------------------
def test_rate_limiter_allows_within_limit():
    clock = {"t": 0.0}
    rl = RateLimiter(limit=3, window_seconds=60, now=lambda: clock["t"])
    assert rl.check("k") == (True, 0)
    assert rl.check("k") == (True, 0)
    assert rl.check("k") == (True, 0)
    allowed, retry = rl.check("k")  # 4th exceeds
    assert allowed is False and retry > 0


def test_rate_limiter_window_resets():
    clock = {"t": 0.0}
    rl = RateLimiter(limit=1, window_seconds=10, now=lambda: clock["t"])
    assert rl.check("k")[0] is True
    assert rl.check("k")[0] is False  # over limit
    clock["t"] = 11.0  # window elapsed
    assert rl.check("k")[0] is True  # allowed again


def test_rate_limiter_per_key_isolation():
    clock = {"t": 0.0}
    rl = RateLimiter(limit=1, window_seconds=10, now=lambda: clock["t"])
    assert rl.check("a")[0] is True
    assert rl.check("b")[0] is True  # different key, own bucket
    assert rl.check("a")[0] is False


def test_rate_limiter_disabled_when_zero():
    rl = RateLimiter(limit=0, window_seconds=60)
    assert not rl.enabled
    for _ in range(100):
        assert rl.check("k") == (True, 0)
