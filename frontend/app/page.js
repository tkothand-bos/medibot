"use client";

import { useRef, useState } from "react";
import { chat, login } from "../lib/api";

const DEMO_USERS = [
  { username: "dr.mehta", role: "doctor" },
  { username: "nurse.priya", role: "nurse" },
  { username: "billing.ravi", role: "billing_executive" },
  { username: "tech.anand", role: "technician" },
  { username: "admin.sys", role: "admin" },
];

export default function Home() {
  const [session, setSession] = useState(null); // {access_token, username, role, collections}
  return session ? (
    <Chat session={session} onLogout={() => setSession(null)} />
  ) : (
    <Login onLogin={setSession} />
  );
}

function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await login(username, password));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>🏥 MediBot</h1>
        <p className="sub">MediAssist Health Network — internal assistant</p>
        <label>Username</label>
        <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {error && <div className="error-banner">{error}</div>}
        <div className="demo-users">
          <h3>Demo accounts (click to fill)</h3>
          {DEMO_USERS.map((u) => (
            <span key={u.username} className="demo-chip" onClick={() => setUsername(u.username)}>
              {u.username} · {u.role}
            </span>
          ))}
        </div>
      </form>
    </div>
  );
}

function Chat({ session, onLogout }) {
  const [messages, setMessages] = useState([
    {
      kind: "bot",
      answer: `Hello ${session.username}! Ask me anything from your permitted collections: ${session.collections.join(", ")}.`,
      sources: [],
      retrieval_type: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  async function send(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question || busy) return;
    setMessages((m) => [...m, { kind: "user", answer: question }]);
    setInput("");
    setBusy(true);
    try {
      const res = await chat(question, session.access_token);
      setMessages((m) => [...m, { kind: "bot", ...res }]);
    } catch (err) {
      setMessages((m) => [...m, { kind: "bot", blocked: true, answer: err.message, sources: [] }]);
    } finally {
      setBusy(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  }

  return (
    <div className="chat-shell">
      <aside className="sidebar">
        <h2>🏥 MediBot</h2>
        <div>
          <div className="section-label">Signed in as</div>
          <div style={{ margin: "0.35rem 0" }}>{session.username}</div>
          <span className="role-badge">{session.role.replace("_", " ")}</span>
        </div>
        <div>
          <div className="section-label">Accessible collections</div>
          {session.collections.map((c) => (
            <span key={c} className="collection-pill">📁 {c}</span>
          ))}
        </div>
        <button className="logout-btn" onClick={onLogout}>Sign out</button>
      </aside>

      <main className="chat-main">
        <div className="messages">
          {messages.map((m, i) =>
            m.kind === "user" ? (
              <div key={i} className="msg user">{m.answer}</div>
            ) : (
              <div key={i} className={`msg bot${m.blocked ? " blocked" : ""}`}>
                {m.answer}
                {(m.retrieval_type || (m.sources && m.sources.length > 0)) && (
                  <>
                    <div className="meta-row">
                      {m.retrieval_type === "hybrid_rag" && <span className="tag hybrid">Hybrid RAG</span>}
                      {m.retrieval_type === "sql_rag" && <span className="tag sql">SQL RAG</span>}
                    </div>
                    {m.sources && m.sources.length > 0 && (
                      <div className="sources">
                        <h4>Sources</h4>
                        {m.sources.map((s, j) => (
                          <div key={j} className="source-line">
                            📄 {s.source_document} — {s.section_title} ({s.collection})
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            )
          )}
          {busy && <div className="typing">MediBot is thinking…</div>}
          <div ref={bottomRef} />
        </div>
        <form className="composer" onSubmit={send}>
          <input
            placeholder="Ask MediBot…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
          />
          <button disabled={busy || !input.trim()}>Send</button>
        </form>
      </main>
    </div>
  );
}
