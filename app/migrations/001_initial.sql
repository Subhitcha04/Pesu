-- v0.1 schema, kept so an existing v0.1 data volume upgrades in place.
CREATE TABLE IF NOT EXISTS children (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, age INTEGER, note TEXT DEFAULT '',
    parent_note TEXT DEFAULT '', word_ids TEXT DEFAULT '[]',
    sessions_per_day INTEGER DEFAULT 2, tries_per_session INTEGER DEFAULT 7,
    is_sample INTEGER DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS clips (
    child_id TEXT, word_id TEXT, kind TEXT, path TEXT, updated_at TEXT,
    PRIMARY KEY (child_id, word_id, kind)
);
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY, child_id TEXT NOT NULL, session_id TEXT, ts TEXT NOT NULL,
    word_id TEXT NOT NULL, pesu_verdict TEXT, verdict TEXT NOT NULL, decided_by TEXT NOT NULL,
    reason TEXT, transcript TEXT, alternatives TEXT, noise_rms REAL, audio_path TEXT,
    is_sample INTEGER DEFAULT 0
);
