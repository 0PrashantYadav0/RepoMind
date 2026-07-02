# RepoMind + n8n (Option C: low-code ingestion)

This is the Phase 2 low-code lane. Instead of writing bot code, wire Slack /
Discord / GitHub trigger nodes in n8n to RepoMind's HTTP ingest endpoint.

## Endpoint

```
POST http://<repomind-host>:8000/ingest/message
Content-Type: application/json

{
  "id": "<unique message id>",      // required (or "message_id")
  "author": "<display name>",
  "content": "<message text>",      // or "text"
  "channel": "<channel name>",
  "thread_id": "<optional parent id>",
  "timestamp": "2026-07-01T10:00:00Z",
  "links": ["https://..."]            // optional; auto-extracted if omitted
}
```

Idempotent: the message id maps to a stable node id, so re-delivery never
creates duplicates. References like `#123` in the text become `discussed-in`
edges to the matching issue/PR (resolved once that entity exists in the graph).

## Example n8n workflow

1. Trigger node: Slack Trigger (event: message) or Discord Trigger.
2. Set node (optional): map the platform payload to the fields above:
   - `id`  <- `{{$json["ts"]}}` (Slack) or `{{$json["id"]}}` (Discord)
   - `author` <- `{{$json["user"]}}` / `{{$json["author"]["username"]}}`
   - `content` <- `{{$json["text"]}}` / `{{$json["content"]}}`
   - `channel` <- channel name
3. HTTP Request node:
   - Method: POST
   - URL: `http://<repomind-host>:8000/ingest/message`
   - Body: JSON, using the mapped fields.

That is the entire pipeline -- no backend code.

## When to use Option C vs Option B (live bots)

| Need | Use |
|---|---|
| Fast, visual, non-engineer-extendable | Option C (n8n) |
| Full control of normalization, backfill, rate-limit handling | Option B (live bots) |

Both produce the SAME Message nodes through the SAME idempotent pipeline, so you
can mix them (e.g. n8n for Slack, a live bot for Discord).
