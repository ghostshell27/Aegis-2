import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function TopicMap() {
  const { trackId } = useParams();
  const navigate = useNavigate();
  const [map, setMap] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const m = await api.getProgressMap();
        setMap(m);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [trackId]);

  if (error) return <div className="error">{error}</div>;
  if (!map) return <div className="notice">Loading topics...</div>;

  const track = map.tracks.find((t) => t.id === trackId);
  if (!track) return <div className="error">Unknown track: {trackId}</div>;

  return (
    <div className="topic-map-wrapper">
      <div>
        <h1>{track.title}</h1>
        <p className="hero-sub">{track.summary}</p>
      </div>

      {track.units.map((unit) => (
        <div key={unit.id} className="unit-block">
          <h2>{unit.title}</h2>
          <div className="topic-row">
            {unit.topics.map((topic) => (
              <TopicNode
                key={topic.id}
                topic={topic}
                onOpen={() => navigate(`/session/new/${topic.id}`)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TopicNode({ topic, onOpen }) {
  return (
    <div
      className={`topic-node ${topic.status}`}
      onClick={onOpen}
      title={topic.prerequisites.length
        ? `Prereqs: ${topic.prerequisites.join(", ")}`
        : "No prerequisites"}
    >
      <div className="status-dot" />
      <div className="title">{topic.title}</div>
      <div className="sub">
        <span>Difficulty {topic.difficulty}</span>
        {topic.attempts ? <span>{topic.correct}/{topic.attempts} correct</span> : null}
      </div>
      <div className="mastery-bar">
        <div className="fill" style={{ width: `${topic.mastery_score}%` }} />
      </div>
    </div>
  );
}
