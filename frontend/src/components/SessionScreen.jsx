import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import ChatMessage from "./ChatMessage.jsx";

export default function SessionScreen({ mode }) {
  const { topicId, sessionId: routeSessionId } = useParams();
  const navigate = useNavigate();

  const [session, setSession] = useState(null);
  const [topic, setTopic] = useState(null);
  const [messages, setMessages] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [exerciseActive, setExerciseActive] = useState(false);
  const [outcome, setOutcome] = useState("ongoing");
  const [phase, setPhase] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);
  const [tokens, setTokens] = useState(0);

  // Conservative default; most modern models support at least this much.
  const TOKEN_BUDGET = 100_000;

  const scrollRef = useRef(null);
  const didStart = useRef(false);
  const didResume = useRef(false);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, busy]);

  useEffect(() => {
    if (mode === "start" && topicId && !didStart.current) {
      didStart.current = true;
      startSession();
    } else if (mode === "resume" && routeSessionId && !didResume.current) {
      didResume.current = true;
      resumeSession(Number(routeSessionId));
    }
  }, [mode, topicId, routeSessionId]);

  const startSession = async () => {
    setStarting(true);
    setError(null);
    try {
      const topicMeta = await api.getTopic(topicId);
      setTopic(topicMeta);

      // If there's an existing in-progress session for this topic, resume
      // it instead of starting fresh. Otherwise the user loses their chat
      // every time they reopen the app.
      try {
        const active = await api.getActiveSession(topicId);
        if (active && active.session_id) {
          navigate(`/session/${active.session_id}`, { replace: true });
          return;
        }
      } catch (_) {
        // If the active-session lookup fails for any reason, fall through
        // and start a brand-new session below.
      }

      const res = await api.startSession({ topic_id: topicId, mode: "learn" });
      setSession({ id: res.session_id, topic_id: topicId });
      setMessages([{ role: "assistant", content: res.assistant_message }]);
      setSuggestions(res.suggestions || []);
      setExerciseActive(!!res.exercise_active);
      setOutcome(res.outcome || "ongoing");
      setPhase(res.metadata?.phase);
      setTokens(res.metadata?.tokens_estimate || 0);
      navigate(`/session/${res.session_id}`, { replace: true });
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  };

  const resumeSession = async (sid) => {
    setStarting(true);
    setError(null);
    try {
      const history = await api.getSessionHistory(sid);
      setSession({ id: sid });
      if (history.topic) setTopic(history.topic);
      if (typeof history.tokens_estimate === "number") {
        setTokens(history.tokens_estimate);
      }
      const msgs = history.messages || [];
      setMessages(msgs.map((m) => ({ role: m.role, content: m.content })));

      // Re-hydrate live UI state from the last assistant turn so chips, the
      // exercise banner, phase tag, and outcome survive a refresh / resume.
      const lastAssistant = [...msgs].reverse().find((m) => m.role === "assistant");
      const raw = lastAssistant?.meta?.raw;
      if (raw) {
        setSuggestions(raw.suggestions || []);
        setExerciseActive(!!raw.exercise_active);
        setOutcome(raw.outcome || "ongoing");
        setPhase(raw.phase || lastAssistant.meta?.phase || null);
      } else if (lastAssistant?.meta?.phase) {
        setPhase(lastAssistant.meta.phase);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  };

  const send = async (action = "answer", overrideContent) => {
    if (!session) return;
    const content = overrideContent !== undefined ? overrideContent : input;
    if (action === "answer" && !content.trim()) return;
    let effectiveAction = action;
    if (action === "answer" && looksLikeDontKnow(content)) {
      effectiveAction = "dont_know";
    }
    setBusy(true);
    setError(null);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: actionLabel(effectiveAction, content) },
    ]);
    setInput("");
    try {
      const res = await api.sendTurn({
        session_id: session.id,
        content: content || actionLabel(effectiveAction, ""),
        action: effectiveAction,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: res.assistant_message }]);
      setSuggestions(res.suggestions || []);
      setExerciseActive(!!res.exercise_active);
      setOutcome(res.outcome || "ongoing");
      setPhase(res.metadata?.phase);
      if (typeof res.metadata?.tokens_estimate === "number") {
        setTokens(res.metadata.tokens_estimate);
      }
    } catch (e) {
      setError(e.message);
      setMessages((prev) => prev.slice(0, -1));
      if (overrideContent === undefined) setInput(content);
    } finally {
      setBusy(false);
    }
  };

  const dontKnow = () => send("dont_know", "I don't know. Please walk me through it Socratically.");
  const giveHint = () => send("hint", "Give me the smallest possible hint.");
  const continueOn = () => send("continue", "Continue.");
  const simpler = () => send("simpler", "Please restate this more simply.");
  const wantExample = () => send("example", "Can I see an example first?");

  const endSession = async (kind = "complete") => {
    if (!session) return;
    try {
      await api.endSession({ session_id: session.id, outcome: kind });
      navigate("/");
    } catch (e) {
      setError(e.message);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (busy) return;
      send("answer");
    }
  };

  if (starting) return <div className="notice">Starting session...</div>;
  if (error && !session) return <div className="error">{error}</div>;
  if (!session) return <div className="notice">Preparing session...</div>;

  return (
    <div className="session-screen">
      <div className="session-header">
        <div className="left">
          {topic ? (
            <>
              <div className="crumbs">
                {topic.track_title} &raquo; {topic.unit_title}
              </div>
              <h1>{topic.title}</h1>
            </>
          ) : (
            <h1>Session #{session.id}</h1>
          )}
          <div className="row" style={{ gap: 8, marginTop: 8 }}>
            {phase ? <span className="tag">{phase}</span> : null}
            {exerciseActive ? <span className="exercise-banner">Exercise active</span> : null}
            {outcome === "correct" ? <span className="outcome-correct">Correct!</span> : null}
            {outcome === "incorrect" ? (
              <span className="outcome-incorrect">
                {"Not quite \u2014 read the consequence below."}
              </span>
            ) : null}
          </div>
        </div>
        <div className="right">
          <button className="btn ghost" onClick={() => endSession("checkpoint")}>
            Save &amp; exit
          </button>
          <button className="btn" onClick={() => endSession("complete")}>
            Finish session
          </button>
        </div>
      </div>

      <ContextBar tokens={tokens} budget={TOKEN_BUDGET} />

      <div className="chat-scroll" ref={scrollRef}>
        {messages.map((m, i) => (
          <ChatMessage key={i} role={m.role} content={m.content} />
        ))}
        {busy ? (
          <div className="chat-message assistant">
            <div className="role-tag">Aegis</div>
            <div className="bubble">
              <em>thinking...</em>
            </div>
          </div>
        ) : null}
      </div>

      {error ? <div className="error">{error}</div> : null}

      {suggestions && suggestions.length ? (
        <div className="suggestions">
          {suggestions.map((s, i) => (
            <button
              key={i}
              className="chip"
              onClick={() => send("answer", s)}
              disabled={busy}
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      <div className="composer">
        <textarea
          placeholder={
            exerciseActive
              ? "Type your answer. Show work if you like \u2014 LaTeX works."
              : "Write a question, an answer, or press Continue."
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={busy}
        />
        <div className="composer-actions">
          <div className="row">
            <button
              className="btn dontknow-btn"
              onClick={dontKnow}
              disabled={busy}
              title='Triggers a Socratic walkthrough. Also works if you type "no se" or "I don&apos;t know".'
            >
              I don&apos;t know
            </button>
            <button className="btn ghost" onClick={giveHint} disabled={busy}>
              Hint
            </button>
            <button className="btn ghost" onClick={simpler} disabled={busy}>
              Simpler, please
            </button>
            <button className="btn ghost" onClick={wantExample} disabled={busy}>
              Example
            </button>
            <button className="btn ghost" onClick={continueOn} disabled={busy}>
              Continue
            </button>
          </div>
          <div className="row">
            <button className="btn primary" onClick={() => send("answer")} disabled={busy}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ContextBar({ tokens, budget }) {
  const pct = Math.min(100, Math.round((tokens * 100) / budget));
  let level = "ok";
  if (pct >= 80) level = "high";
  else if (pct >= 50) level = "mid";
  const fmt = (n) => n.toLocaleString();
  return (
    <div className={`context-bar ${level}`}>
      <div className="context-bar-label">
        <span>Context</span>
        <span className="context-bar-numbers">
          ~{fmt(tokens)} / {fmt(budget)} tokens · {pct}%
        </span>
      </div>
      <div className="context-bar-track">
        <div className="context-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function actionLabel(action, content) {
  const text = (content || "").trim();
  if (action === "answer") {
    if (text && looksLikeDontKnow(text)) {
      return "(I don't know \u2014 please walk me through it.)";
    }
    return text || "(no answer)";
  }
  if (action === "continue") return "(continue)";
  if (action === "simpler") return "(please simpler)";
  if (action === "example") return "(show me an example)";
  if (action === "hint") return "(give a small hint)";
  if (action === "dont_know") return "(I don't know)";
  return text;
}

function looksLikeDontKnow(text) {
  // Normalize: lowercase, strip diacritics (so "s\u00e9" -> "se"), drop punctuation.
  const t = (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return (
    t === "no se" ||
    t === "nose" ||
    t === "i dont know" ||
    t === "i do not know" ||
    t === "dont know" ||
    t === "no idea" ||
    t === "ni idea" ||
    t === "no lo se"
  );
}
