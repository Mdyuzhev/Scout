CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS research_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic           TEXT NOT NULL,
    config          JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    documents_count INT  DEFAULT 0,
    chunks_count    INT  DEFAULT 0,
    brief           TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    search_vector   TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('russian', topic)
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_sessions_search  ON research_sessions USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_sessions_status  ON research_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON research_sessions(created_at DESC);
