import json, os, sqlite3
from datetime import datetime, timezone

def _path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    return url.split("sqlite:///", 1)[1] if url.startswith("sqlite:///") else url

def _conn():
    p = _path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(p, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init_db():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT, created_at TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")
        c.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, system_prompt TEXT)")

def ping() -> bool:
    try:
        with _conn() as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False

def get_history(sid):
    with _conn() as c:
        rows = c.execute("SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    return [{"role": r, "content": t, **({"metadata": json.loads(m)} if m else {})} for r, t, m in rows]

def get_prompt(sid):
    with _conn() as c:
        r = c.execute("SELECT system_prompt FROM sessions WHERE session_id=?", (sid,)).fetchone()
    return r[0] if r else None

def save_exchange(sid, user_text, reply, metadata, system_prompt=None):
    """Atomic write of both turns; only called after a successful completion."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO sessions(session_id) VALUES (?)", (sid,))
        if system_prompt is not None:
            c.execute("UPDATE sessions SET system_prompt=? WHERE session_id=?", (system_prompt, sid))
        c.execute("INSERT INTO messages(session_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)", (sid, "user", user_text, None, now))
        c.execute("INSERT INTO messages(session_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)", (sid, "assistant", reply, json.dumps(metadata), now))
