import os, time
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from . import db, llm

DEFAULT_SYSTEM_PROMPT = "You are a helpful, concise assistant."
app = FastAPI(title="LLM Chatbot")
app.add_middleware(CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup():
    db.init_db()

@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    return JSONResponse({"detail": "internal server error"}, status_code=500)

class ChatIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str
    system_prompt: str | None = None

    @field_validator("message")
    @classmethod
    def _msg(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= 4000:
            raise ValueError("message must be 1-4000 characters after trimming")
        return v

@app.get("/health")
def health():
    if not db.ping():
        raise HTTPException(503, "database unreachable")
    return {"status": "ok", "keys_configured": len(llm.get_keys()), "cache_enabled": llm.cache_enabled()}

@app.post("/chat")
def chat(body: ChatIn, x_simulate_failure: str | None = Header(default=None)):
    t0 = time.perf_counter()
    prompt = body.system_prompt or db.get_prompt(body.session_id) or DEFAULT_SYSTEM_PROMPT
    history = [{"role": m["role"], "content": m["content"]} for m in db.get_history(body.session_id)]
    messages = [{"role": "system", "content": prompt}, *history, {"role": "user", "content": body.message}]
    try:
        r = llm.complete(messages, llm.parse_simulation(x_simulate_failure))
    except llm.AllProvidersUnavailable:
        raise HTTPException(503, "all providers unavailable")
    meta = {"resolution_source": "LLM_CACHE" if r["cache_hit"] else "LIVE_INFERENCE",
            "model": r["model"], "latency_ms": 0, "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"], "key_id": r["key_id"], "fallback_attempts": r["fallback_attempts"]}
    meta["latency_ms"] = max(1, int((time.perf_counter() - t0) * 1000))
    db.save_exchange(body.session_id, body.message, r["reply"], meta, body.system_prompt)
    return {"session_id": body.session_id, "reply": r["reply"], "metadata": meta}

@app.get("/sessions/{session_id}/messages")
def messages(session_id: str):
    msgs = db.get_history(session_id)
    if not msgs:
        raise HTTPException(404, "session not found")
    return {"session_id": session_id, "messages": msgs}
