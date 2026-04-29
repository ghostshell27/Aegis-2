import React, { useEffect, useState, useCallback } from "react";
import { Routes, Route, Navigate, NavLink } from "react-router-dom";
import { api } from "./api.js";
import HomeScreen from "./components/HomeScreen.jsx";
import TopicMap from "./components/TopicMap.jsx";
import SessionScreen from "./components/SessionScreen.jsx";
import ConfigScreen from "./components/ConfigScreen.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";

export default function App() {
  const [configured, setConfigured] = useState(null);
  const [error, setError] = useState(null);

  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await api.getConfig();
      setConfigured(cfg.configured);
      setError(null);
    } catch (e) {
      setError(e.message);
      setConfigured(false);
    }
  }, []);

  useEffect(() => {
    refreshConfig();
  }, [refreshConfig]);

  if (configured === null) {
    return (
      <div className="app-shell loading">
        <div className="spinner" />
        <p>Starting Aegis 2...</p>
        {error ? <p className="error">{error}</p> : null}
      </div>
    );
  }

  if (!configured) {
    return (
      <div className="app-shell">
        <Header configured={false} />
        <main className="app-main">
          <ConfigScreen onSaved={refreshConfig} firstRun />
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Header configured={true} />
      <main className="app-main">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<HomeScreen />} />
            <Route path="/track/:trackId" element={<TopicMap />} />
            <Route path="/session/new/:topicId" element={<SessionScreen mode="start" />} />
            <Route path="/session/:sessionId" element={<SessionScreen mode="resume" />} />
            <Route path="/config" element={<ConfigScreen onSaved={refreshConfig} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}

function BrandMark() {
  // Inline SVG so the glyph renders identically regardless of font
  // availability and there is no chance of text-encoding mishaps.
  return (
    <svg
      className="brand-mark"
      viewBox="0 0 32 32"
      width="28"
      height="28"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="brandGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#93c5fd" />
          <stop offset="100%" stopColor="#c4b5fd" />
        </linearGradient>
      </defs>
      {/* Stylised alpha glyph: a leaning loop crossed by a tail. */}
      <path
        d="M11.6 9.6c-3.4 0-5.8 3-5.8 7.1 0 4 2 6.7 5.4 6.7 2.4 0 4.1-1.4 5.2-3.5l1.6 3.2h4.4l-3.7-6.6c.7-1.7 1-3.4 1-4.9V11h-3.6v.7c0 .7-.1 1.5-.3 2.3-.7-2.6-2.3-4.4-4.2-4.4zm.5 3.2c1.6 0 2.7 1.7 2.7 4 0 2.4-1.1 4-2.7 4-1.5 0-2.6-1.6-2.6-4 0-2.3 1.1-4 2.6-4z"
        fill="url(#brandGrad)"
      />
    </svg>
  );
}

function Header({ configured }) {
  return (
    <header className="app-header">
      <div className="brand">
        <BrandMark />
        <span className="brand-name">Aegis 2</span>
      </div>
      {configured ? (
        <nav className="top-nav">
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/track/algebra">Algebra</NavLink>
          <NavLink to="/track/calculus">Calculus</NavLink>
          <NavLink to="/config">Settings</NavLink>
        </nav>
      ) : null}
    </header>
  );
}
