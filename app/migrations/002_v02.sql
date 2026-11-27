-- v0.2: foreign keys with cascade (A12/A14), UTC 'Z' timestamps (A3), audit trail (A11),
-- confidence/latency (A17/B8), audio MIME (A6), sessions + stickers (A1/B13), settings (A5).
-- SQLite cannot add a foreign key to an existing table, so tables are rebuilt and copied.

CREATE TABLE children_v2 (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
    age INTEGER NOT NULL CHECK (age BETWEEN 2 AND 12),
    note TEXT NOT NULL DEFAULT '',
    parent_note TEXT NOT NULL DEFAULT '',
    word_ids TEXT NOT NULL DEFAULT '[]',
    sessions_per_day INTEGER NOT NULL DEFAULT 2,
    tries_per_session INTEGER NOT NULL DEFAULT 7,
    listen_first INTEGER,                 -- NULL = automatic (on for age <= 3)
    is_sample INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
INSERT INTO children_v2 (id, name, age, note, parent_note, word_ids, sessions_per_day, tries_per_session, is_sample, created_at)
    SELECT id, name, COALESCE(age, 4), COALESCE(note, ''), COALESCE(parent_note, ''), COALESCE(word_ids, '[]'),
           COALESCE(sessions_per_day, 2), COALESCE(tries_per_session, 7), COALESCE(is_sample, 0),
           CASE WHEN created_at LIKE '%Z' THEN created_at ELSE substr(COALESCE(created_at, '2026-01-01T00:00:00'), 1, 19) || 'Z' END
    FROM children;
DROP TABLE children;
ALTER TABLE children_v2 RENAME TO children;

CREATE TABLE clips_v2 (
    child_id TEXT NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    word_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('prompt', 'cue')),
    path TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT 'audio/webm',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (child_id, word_id, kind)
);
INSERT INTO clips_v2 (child_id, word_id, kind, path, updated_at)
    SELECT child_id, word_id, kind, path, COALESCE(updated_at, '2026-01-01T00:00:00Z') FROM clips
    WHERE child_id IN (SELECT id FROM children);
DROP TABLE clips;
ALTER TABLE clips_v2 RENAME TO clips;

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    child_id TEXT NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,
    stars INTEGER NOT NULL DEFAULT 0,
    sticker_id TEXT,
    is_sample INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE attempts_v2 (
    id TEXT PRIMARY KEY,
    child_id TEXT NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    session_id TEXT,
    ts TEXT NOT NULL,
    word_id TEXT NOT NULL,
    pesu_verdict TEXT NOT NULL,           -- immutable first pass
    verdict TEXT NOT NULL CHECK (verdict IN ('correct', 'error_t', 'unsure', 'unscored')),
    decided_by TEXT NOT NULL CHECK (decided_by IN ('pesu', 'parent', 'therapist', 'none')),
    reason TEXT NOT NULL DEFAULT '',
    transcript TEXT NOT NULL DEFAULT '',
    alternatives TEXT NOT NULL DEFAULT '[]',
    confidence REAL,
    noise_rms REAL,
    latency_ms INTEGER,
    audio_path TEXT,
    audio_mime TEXT,
    is_sample INTEGER NOT NULL DEFAULT 0
);
INSERT INTO attempts_v2 (id, child_id, session_id, ts, word_id, pesu_verdict, verdict, decided_by, reason,
                         transcript, alternatives, noise_rms, audio_path, audio_mime, is_sample)
    SELECT id, child_id, session_id,
           CASE WHEN ts LIKE '%Z' THEN ts ELSE substr(ts, 1, 19) || 'Z' END,
           word_id, COALESCE(pesu_verdict, verdict), verdict, decided_by, COALESCE(reason, ''),
           COALESCE(transcript, ''), COALESCE(alternatives, '[]'), noise_rms, audio_path,
           CASE WHEN audio_path IS NULL THEN NULL WHEN audio_path LIKE '%.ogg' THEN 'audio/ogg' ELSE 'audio/webm' END,
           COALESCE(is_sample, 0)
    FROM attempts WHERE child_id IN (SELECT id FROM children);
DROP TABLE attempts;
ALTER TABLE attempts_v2 RENAME TO attempts;
CREATE INDEX idx_attempts_child_ts ON attempts (child_id, ts);

CREATE TABLE verdict_events (            -- append-only audit trail (A11)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL CHECK (actor IN ('pesu', 'parent', 'therapist')),
    from_verdict TEXT,
    to_verdict TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_events_attempt ON verdict_events (attempt_id);

CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
