-- MathCore initial schema.
-- Every table is created IF NOT EXISTS so reruns are safe. Future migrations
-- must be additive (new columns / new tables) to preserve user data.

CREATE TABLE IF NOT EXISTS app_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    api_key_ciphertext BLOB NOT NULL,
    base_url TEXT NOT NULL DEFAULT 'https://api.anthropic.com',
    model_name TEXT NOT NULL,
    custom_system_prompt TEXT NOT NULL DEFAULT '',
    provider_hint TEXT NOT NULL DEFAULT 'auto',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    display_name TEXT NOT NULL DEFAULT 'Learner',
    preferred_style TEXT NOT NULL DEFAULT 'balanced',
    preferred_domain TEXT,
    total_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topic_progress (
    topic_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    mastery_score INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    time_seconds INTEGER NOT NULL DEFAULT 0,
    last_session_id INTEGER,
    last_summary TEXT NOT NULL DEFAULT '',
    error_patterns TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_topic_progress_track ON topic_progress(track_id);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    domain TEXT,
    outcome TEXT NOT NULL DEFAULT 'in_progress',
    summary TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'learn'
);

CREATE INDEX IF NOT EXISTS idx_sessions_topic ON sessions(topic_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    meta TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);

CREATE TABLE IF NOT EXISTS exercise_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    user_answer TEXT NOT NULL,
    correct INTEGER NOT NULL DEFAULT 0,
    concept_tag TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS capstone_progress (
    track_id TEXT PRIMARY KEY,
    phase TEXT NOT NULL DEFAULT 'not_started',
    checkpoints TEXT NOT NULL DEFAULT '[]',
    scratchpad TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS domain_stats (
    domain TEXT PRIMARY KEY,
    sessions_used INTEGER NOT NULL DEFAULT 0,
    engagement_score INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
