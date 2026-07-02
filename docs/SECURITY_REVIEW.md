# RepoMind Security and Bug Self-Review

A self-iteration pass over the full Phase 1 + Phase 2 codebase. Each finding has
a severity, the risk, and the fix applied (or the decision to accept it).

## Method
- Automated: `ruff --select S,B,A,RUF,PERF` (flake8-bandit, bugbear, builtins,
  ruff-specific, perf). Result: no real vulnerabilities; 2 false positives on
  env-var names (`secret_env`, `github_token_env` are NOT secrets, just the
  NAMES of env vars), and style/perf nits.
- Manual: threat-modeled every externally reachable surface (the HTTP API and
  the webhook receiver) plus the data pipeline.

## Findings and fixes

### SEC-1 (High) Webhook failed open when no secret configured
Before: if `REPOMIND_WEBHOOK_SECRET` was unset, signature verification was
SKIPPED, so anyone who could reach `/webhook` could inject arbitrary graph data.
Fix: fail-closed. New `webhook.require_signature` (default true). If webhooks are
enabled, signatures are required unless an operator explicitly opts out for a
trusted private network. No secret + required signature => 401.

### SEC-2 (High) Endpoints had no authentication -> now MANDATORY, fail-closed
Before: endpoints were open; an early fix added optional auth only on mutating
routes. Hardened further per requirement: **every endpoint now requires a valid
API key** (supplied as `X-API-Key` or `Authorization: Bearer <token>`), read from
the env var named by `api.token_env` (default `REPOMIND_API_TOKEN`).
- Fail-closed: if the server has no token configured, protected endpoints return
  503 (refuse to serve) instead of falling open.
- Missing/invalid key returns 401. Keys are compared in constant time
  (`hmac.compare_digest`).
- `/livez` is the only open endpoint (liveness probe, returns no data).
- `/webhook` is exempt from the API key because GitHub authenticates it via HMAC
  signature (see SEC-1); it is itself fail-closed.
Verified live with curl against a running server: open=200 on /livez; 401 on
missing/wrong key; 200 with a valid key; 503 when the server token is unset.

### SEC-3 (Medium) Malformed webhook body caused a 500
Before: `json.loads(body)` on a bad payload raised, surfacing a 500 and a stack
trace. Fix: catch and return 400 (bad request) with a clean message.

### BUG-1 (Medium) Latent async bug in the Cognee adapter
`_run()` used `asyncio.ensure_future` when an event loop was already running,
returning an un-awaited Future instead of a result. Harmless in the current
sync-route usage, but a trap. Fix: when a loop is running, execute the coroutine
on a dedicated thread via `asyncio.run`, always returning a real result.

### SEC-4 (Low) Best-effort forget swallowed all exceptions silently
`forget()` used a bare `try/except: pass`. Fix: log at debug level so failures
are observable, while remaining best-effort (local structural removal already
happened, so memory is still consistent).

### Accepted / not changed (with rationale)
- S105 env-var-name false positives: suppressed with a targeted per-file ignore;
  these are configuration field names, not credentials.
- No rate limiting on the API: acceptable for the documented single-operator /
  trusted-network scope; a reverse proxy is the right layer for this in
  production. Noted as future work.
- Message/body size limits: relying on the ASGI server defaults; an explicit cap
  is noted as future work for hardening against oversized payloads.

## Verification
- Regression: full test suite stays green after every fix.
- New tests added for SEC-1 (fail-closed), SEC-2 (auth required/allowed),
  and SEC-3 (400 on malformed body).
