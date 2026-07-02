"""FastAPI app: webhook receiver, manual sync, query, and graph endpoints.

Run: uvicorn repomind.api:create_app --factory
Configure via REPOMIND_CONFIG=path/to/config.yaml

Security model (fail-closed):
  - EVERY endpoint requires a valid API key, supplied as either
    `X-API-Key: <token>` or `Authorization: Bearer <token>`.
  - The token is read from the env var named by `api.token_env`
    (default REPOMIND_API_TOKEN). If it is not set, protected endpoints
    return 503 -- the server refuses to serve rather than falling open.
  - `/webhook` is exempt from the API key because it is authenticated by
    GitHub's HMAC signature (GitHub cannot send a bearer token); it is itself
    fail-closed via `webhook.require_signature`.
  - `/livez` is an unauthenticated liveness probe that returns NO data.
"""
from __future__ import annotations

import json
import os
import pathlib

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from repomind.auth import build_rate_limiter, build_registry, has_scope
from repomind.config import load_config
from repomind.engine import Engine
from repomind.webhook import verify_signature

UI_DIR = pathlib.Path(__file__).parent / "ui"


class AskRequest(BaseModel):
    question: str
    limit: int = 5


class SyncRequest(BaseModel):
    scope: str = "all"
    mode: str = "incremental"


class ForgetRequest(BaseModel):
    target: str


class MessageIngestRequest(BaseModel):
    # n8n / low-code path: a loose chat message. message_id (or id) is required.
    message_id: str | None = None
    id: str | None = None
    author: str | None = None
    text: str | None = None
    content: str | None = None
    channel: str = ""
    thread_id: str | None = None
    timestamp: str | None = None
    links: list[str] | None = None


def create_app(engine: Engine | None = None) -> FastAPI:
    config = load_config(os.environ.get("REPOMIND_CONFIG"))
    eng = engine or Engine(config)
    registry = build_registry(config)
    limiter = build_rate_limiter(config)

    def _extract_token(x_api_key: str | None, authorization: str | None) -> str | None:
        if x_api_key:
            return x_api_key
        if authorization and authorization.startswith("Bearer "):
            return authorization[len("Bearer ") :]
        return None

    def require(scope: str):
        """Build a dependency that requires a key with at least `scope`, then
        applies the per-key rate limit. Fail-closed at every step."""

        def _dep(
            x_api_key: str | None = Header(default=None),
            authorization: str | None = Header(default=None),
        ) -> None:
            if registry.empty:
                # No keys configured at all -> refuse, never fall open.
                raise HTTPException(
                    status_code=503,
                    detail="server has no API keys configured",
                )
            key = registry.match(_extract_token(x_api_key, authorization))
            if key is None:
                raise HTTPException(
                    status_code=401,
                    detail="missing or invalid API key",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not has_scope(key, scope):
                raise HTTPException(
                    status_code=403,
                    detail=f"key '{key.name}' lacks required scope '{scope}'",
                )
            allowed, retry_after = limiter.check(key.name)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )

        return _dep

    app = FastAPI(title="RepoMind", version="0.1.0")
    app.state.engine = eng
    app.state.config = config
    read = [Depends(require("read"))]
    write = [Depends(require("write"))]
    admin = [Depends(require("admin"))]

    @app.get("/livez")
    def livez() -> dict:
        # Unauthenticated liveness probe. Intentionally leaks no data.
        return {"status": "ok"}

    @app.get("/health", dependencies=read)
    def health() -> dict:
        return {"status": "ok", "counts": eng.counts()}

    @app.post("/ask", dependencies=read)
    def ask(req: AskRequest) -> dict:
        return eng.query(req.question, limit=req.limit)

    @app.get("/graph", dependencies=read)
    def graph() -> dict:
        nodes = [
            {
                "id": n.id,
                "type": n.type.value,
                "title": n.title,
                "status": n.status,
                "deleted_in": n.deleted_in,
            }
            for n in eng.store.all_nodes(include_deleted=True)
        ]
        edges = [{"src": e.src, "dst": e.dst, "type": e.type.value} for e in eng.store.all_edges()]
        return {"nodes": nodes, "edges": edges, "counts": eng.counts()}

    @app.post("/sync", dependencies=write)
    def sync(req: SyncRequest) -> dict:
        return eng.sync(scope=req.scope, mode=req.mode)

    @app.post("/verify", dependencies=write)
    def verify(req: SyncRequest) -> dict:
        return eng.verify(scope=req.scope)

    @app.post("/forget", dependencies=admin)
    def forget(req: ForgetRequest) -> dict:
        ok = eng.forget(req.target)
        return {"forgotten": ok, "target": req.target}

    @app.post("/ingest/message", dependencies=write)
    def ingest_message(req: MessageIngestRequest) -> dict:
        # Option C (n8n) and live-bot relay both land here.
        return eng.ingest_chat_dict(req.model_dump())

    @app.post("/webhook")
    async def webhook(
        request: Request,
        x_github_event: str | None = Header(default=None),
        x_github_delivery: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
    ) -> dict:
        # Authenticated by GitHub's HMAC signature, not the API key.
        if not config.webhook.enabled:
            raise HTTPException(status_code=503, detail="webhooks disabled")
        body = await request.body()
        secret = config.webhook_secret()
        # SEC-1: fail-closed. If signatures are required, a secret MUST be set and
        # the signature MUST verify; otherwise reject.
        if config.webhook.require_signature:
            if not secret:
                raise HTTPException(status_code=401, detail="webhook secret not configured")
            if not verify_signature(secret, body, x_hub_signature_256):
                raise HTTPException(status_code=401, detail="invalid signature")
        elif secret:
            # Opted out of requiring signatures, but if a secret exists, still verify.
            if not verify_signature(secret, body, x_hub_signature_256):
                raise HTTPException(status_code=401, detail="invalid signature")
        # SEC-3: malformed JSON -> 400, not 500.
        try:
            payload = json.loads(body or b"{}")
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="invalid JSON body") from None
        return eng.handle_webhook(x_github_event or "", payload, x_github_delivery)

    # Serve the static web UI (unauthenticated assets; all data calls still need
    # an API key). Root redirects to the UI.
    if UI_DIR.is_dir():
        @app.middleware("http")
        async def _no_cache_ui(request: Request, call_next):
            # The UI assets change between deploys; force the browser to always
            # revalidate so a stale app.js/styles.css can never be served.
            response = await call_next(request)
            path = request.url.path
            if path == "/" or path.startswith("/ui"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response

        @app.get("/")
        def root() -> RedirectResponse:
            return RedirectResponse(url="/ui/")

        app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

    return app
