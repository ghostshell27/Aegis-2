import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function HomeScreen() {
  const [map, setMap] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const [m, s] = await Promise.all([api.getProgressMap(), api.getSummary()]);
        setMap(m);
        setSummary(s);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, []);

  if (error) return <div className="error">{error}</div>;
  if (!map || !summary) return <div className="notice">Loading progress...</div>;

  const totals = summary.totals || {};
  const accuracy = totals.total_attempts
    ? Math.round((totals.total_correct * 100) / totals.total_attempts)
    : 0;

  return (
    <>
      <section className="home-hero">
        <h1>Welcome back, {summary.display_name}.</h1>
        <p className="hero-sub">
          Aegis 2 is an AI tutor for Algebra and Calculus. Pick a track below to open
          its topic map, or resume where you left off. Answer wrong and the AI will
          show you what would happen in the real world; press the "I don't know"
          button any time for a Socratic walkthrough.
        </p>
        <div className="hero-stats">
          <Stat value={totals.topics_started || 0} label="Topics opened" />
          <Stat value={totals.topics_mastered || 0} label="Topics mastered" />
          <Stat value={totals.total_attempts || 0} label="Exercises tried" />
          <Stat value={`${accuracy}%`} label="Accuracy" />
          <Stat
            value={summary.preferred_domain || "rotating"}
            label="Preferred domain"
          />
        </div>
      </section>

      <div className="track-grid">
        {map.tracks.map((track) => {
          const totalTopics = track.units.reduce((s, u) => s + u.topics.length, 0);
          const masteredTopics = track.units.reduce(
            (s, u) => s + u.topics.filter((t) => t.status === "mastered").length,
            0,
          );
          const pct = totalTopics ? Math.round((masteredTopics * 100) / totalTopics) : 0;
          return (
            <div
              key={track.id}
              className="card track-card"
              onClick={() => navigate(`/track/${track.id}`)}
            >
              <h2>{track.title}</h2>
              <p>{track.summary}</p>
              <div className="track-meta">
                <span>{track.units.length} units</span>
                <span>{totalTopics} topics</span>
                <span>
                  {masteredTopics}/{totalTopics} mastered
                </span>
              </div>
              <div className="track-progress-bar">
                <div className="fill" style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
