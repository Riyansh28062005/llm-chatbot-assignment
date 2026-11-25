import { useEffect, useRef, useState } from "react";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const newId = () => "s-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

export default function App() {
  const [sessionId] = useState(newId); // new session on every page load
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [system, setSystem] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [items, busy]);

  async function send() {
    const message = text.trim();
    if (!message || busy) return;
    setText(""); setBusy(true);
    setItems((i) => [...i, { role: "user", content: message }]);
    try {
      const body = { session_id: sessionId, message };
      if (system.trim()) body.system_prompt = system.trim();
      const res = await fetch(`${API}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      console.log("chat response", res.status, data);
      if (!res.ok) {
        const d = data.detail;
        const msg = res.status === 503 ? "All AI providers are unavailable right now. Try again in a moment."
          : Array.isArray(d) ? "Your message was rejected: " + d.map((e) => e.msg).join("; ")
          : typeof d === "string" ? d : `Request failed (${res.status}).`;
        setItems((i) => [...i, { role: "error", content: msg }]);
      } else {
        setItems((i) => [...i, { role: "assistant", content: String(data.reply ?? ""), meta: data.metadata || {} }]);
      }
    } catch {
      setItems((i) => [...i, { role: "error", content: "Cannot reach the server. Check your connection and try again." }]);
    } finally { setBusy(false); }
  }

  return (
    <main className="app">
      <header><h1>Chat</h1><span className="sid">session {sessionId}</span></header>
      <details className="sys"><summary>System prompt</summary>
        <textarea data-testid="system-prompt-input" value={system} onChange={(e) => setSystem(e.target.value)} placeholder="Optional. Overrides the default for this session." rows={2} />
      </details>
      <section className="log" aria-live="polite">
        {items.length === 0 && <p className="empty">Ask anything. Repeat a question in a new tab to see a cached answer.</p>}
        {items.map((m, i) => m.role === "assistant" ? (
          <article key={i} className="msg bot" data-testid="assistant-message">
            <p>{m.content}</p>
            <dl className="meta">
              <div><dt>source</dt><dd data-testid="meta-source" className={m.meta.resolution_source === "LLM_CACHE" ? "hit" : ""}>{m.meta.resolution_source}</dd></div>
              <div><dt>model</dt><dd data-testid="meta-model">{m.meta.model}</dd></div>
              <div><dt>latency</dt><dd data-testid="meta-latency">{m.meta.latency_ms} ms</dd></div>
              <div><dt>input tokens</dt><dd data-testid="meta-input-tokens">{m.meta.input_tokens}</dd></div>
              <div><dt>output tokens</dt><dd data-testid="meta-output-tokens">{m.meta.output_tokens}</dd></div>
              {(m.meta.fallback_attempts ?? 0) > 0 && <div><dt>failover</dt><dd>{m.meta.fallback_attempts} key(s) skipped, answered by {m.meta.key_id}</dd></div>}
            </dl>
          </article>
        ) : (
          <article key={i} className={"msg " + (m.role === "error" ? "err" : "me")} role={m.role === "error" ? "alert" : undefined}><p>{m.content}</p></article>
        ))}
        {busy && <p className="empty">Thinking…</p>}
        <div ref={end} />
      </section>
      <div className="composer">
        <textarea data-testid="chat-input" value={text} rows={2} placeholder="Type a message" disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <button data-testid="send-button" onClick={send} disabled={busy || !text.trim()}>Send</button>
      </div>
    </main>
  );
}
