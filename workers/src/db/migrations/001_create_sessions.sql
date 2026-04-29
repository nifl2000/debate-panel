-- workers/src/db/migrations/001_create_sessions.sql
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  topic TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'COMPLETED',
  config TEXT NOT NULL,
  agents TEXT NOT NULL,
  messages TEXT NOT NULL,
  synthesis TEXT,
  moderator_name TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  expires_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
