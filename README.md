# LLM Chatbot with Key Failover and Response Caching

React + FastAPI + SQLite, with LiteLLM as the gateway.

## 1. Live URLs
- Frontend: _add after deploying_
- Backend: _add after deploying_ (`/health`)

## 2. Run locally
**With Docker:** `cp .env.example .env`, put 2+ real keys in `LLM_API_KEYS`, then `make up`.
Frontend http://localhost:3000, backend http://localhost:8000. `make down` stops it. The SQLite file lives in the `appdata` volume at `/data/app.db`.

**Without Docker:**
```bash
cd backend && pip install -r requirements.txt
export LLM_API_KEYS=key1,key2 ENABLE_FAILURE_SIMULATION=true ALLOWED_ORIGINS=http://localhost:3000
uvicorn app.main:app --port 8000
cd ../frontend && npm install && VITE_API_URL=http://localhost:8000 npm run dev   # :3000
```
Tests: `make test` (uses `LLM_MOCK=true`, so no keys or network needed).

## 3. Design decisions
- **Key fallback:** `LLM_API_KEYS` is an ordered pool (`key_1`, `key_2`, ...). Keys are tried in order via `litellm.completion(api_key=...)`. Any failure (429, quota, 5xx, timeout) moves to the next key and increments `fallback_attempts`. If all fail the API returns `503 {"detail":"all providers unavailable"}` and nothing is stored. Only `key_id` is exposed, never a key.
- **Caching:** LiteLLM's in-memory cache (`Cache(type="local")`). The key is the model plus the full message list (system + history + new message), so the same first message in a new session hits and any other message misses. Hits are detected from LiteLLM's `cache_hit` flag; reply and token usage are the stored ones and `key_id` is `null`. The cache is per process and resets on restart.
- **SQLite sessions:** the spec's `messages` table plus a `sessions` table for the per-session system prompt. Schema is created on startup. Both turns are written in one transaction only after a successful reply; history is rebuilt from SQLite on every request.
- **Failure simulation:** `X-Simulate-Failure` is parsed per request and honored only when `ENABLE_FAILURE_SIMULATION=true`. Simulated keys are skipped before any provider call, so successful answers are always real.

## 4. Verification
```bash
H='Content-Type: application/json'
curl -s -H "$H" localhost:8000/chat -d '{"session_id":"a","message":"Capital of France?"}'   # LIVE_INFERENCE
curl -s -H "$H" localhost:8000/chat -d '{"session_id":"b","message":"Capital of France?"}'   # LLM_CACHE, key_id null, faster
curl -s -H "$H" -H 'X-Simulate-Failure: key_1=429' localhost:8000/chat -d '{"session_id":"a","message":"And Germany?"}'  # key_2, fallback_attempts 1
curl -s -H "$H" -H 'X-Simulate-Failure: *=429' localhost:8000/chat -d '{"session_id":"a","message":"x"}'  # 503
curl -s localhost:8000/sessions/a/messages
```
In the UI every reply shows source, model, latency and per-request input/output tokens.

## 5. Setup Used
Claude (chat) for code generation; pytest for backend tests.

## 6. Bonus features
- Optional system-prompt field, stored per session.
- `LLM_MOCK=true` mode so tests and demos run offline.
