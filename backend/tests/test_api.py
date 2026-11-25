import os, uuid
os.environ.update(LLM_MOCK="true", LLM_API_KEYS="k1,k2", ENABLE_FAILURE_SIMULATION="true",
                  DATABASE_URL=f"sqlite:////tmp/test-{uuid.uuid4().hex}.db")
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client

def sid(): return "s-" + uuid.uuid4().hex[:8]
def chat(c, s, m, **kw): return c.post("/chat", json={"session_id": s, "message": m}, **kw)

def test_health(c):
    assert c.get("/health").json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}

def test_cache_hit_across_sessions(c):
    m = "unique question " + uuid.uuid4().hex
    a = chat(c, sid(), m).json(); b = chat(c, sid(), m).json()
    assert a["metadata"]["resolution_source"] == "LIVE_INFERENCE" and a["metadata"]["key_id"] == "key_1"
    assert b["metadata"]["resolution_source"] == "LLM_CACHE" and b["metadata"]["key_id"] is None
    assert a["reply"] == b["reply"] and b["metadata"]["fallback_attempts"] == 0
    assert b["metadata"]["input_tokens"] == a["metadata"]["input_tokens"]
    assert b["metadata"]["latency_ms"] < a["metadata"]["latency_ms"]
    assert chat(c, sid(), m + " different").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"

def test_multi_turn_and_isolation(c):
    s, o = sid(), sid()
    chat(c, s, "my name is Zed " + s); r = chat(c, s, "what is my name?").json()
    assert "Zed" in r["reply"]
    assert [m["role"] for m in c.get(f"/sessions/{s}/messages").json()["messages"]] == ["user", "assistant"] * 2
    chat(c, o, "hi " + o)
    assert len(c.get(f"/sessions/{o}/messages").json()["messages"]) == 2

def test_failover(c):
    r = chat(c, sid(), "f1 " + uuid.uuid4().hex, headers={"X-Simulate-Failure": "key_1=429"}).json()
    assert r["metadata"]["key_id"] == "key_2" and r["metadata"]["fallback_attempts"] == 1
    r = chat(c, sid(), "f2 " + uuid.uuid4().hex, headers={"X-Simulate-Failure": "key_1=500"}).json()
    assert r["metadata"]["key_id"] == "key_2"

def test_all_fail_503_not_stored(c):
    s = sid()
    for h in ("*=429", "key_1=429,key_2=500"):
        r = chat(c, s, "x " + uuid.uuid4().hex, headers={"X-Simulate-Failure": h})
        assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert c.get(f"/sessions/{s}/messages").status_code == 404

def test_validation_and_404(c):
    assert c.post("/chat", json={"session_id": "a", "message": "   "}).status_code == 422
    assert c.post("/chat", json={"session_id": "", "message": "hi"}).status_code == 422
    assert c.post("/chat", json={"session_id": "a", "message": "x" * 4001}).status_code == 422
    assert c.post("/chat", json={"message": "hi"}).status_code == 422
    assert c.post("/chat", content="{bad", headers={"content-type": "application/json"}).status_code == 422
    r = c.get("/sessions/nope/messages")
    assert r.status_code == 404 and r.json() == {"detail": "session not found"}
