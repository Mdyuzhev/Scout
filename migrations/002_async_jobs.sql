CREATE TABLE IF NOT EXISTS async_jobs (
    job_id          TEXT PRIMARY KEY,
    topic           TEXT NOT NULL,
    query           TEXT NOT NULL,
    model           TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    stage           TEXT NOT NULL DEFAULT 'queued',
    message         TEXT,
    total_urls      INT DEFAULT 0,
    auto_collected  INT DEFAULT 0,
    test_docs       INT,
    test_chunks     INT,
    test_failed     INT,
    session_id      TEXT,
    documents_count INT,
    chunks_count    INT,
    failed_count    INT,
    blocked_count   INT,
    brief           TEXT,
    tokens_used     INT,
    sources_used    INT,
    saved_to        TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON async_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON async_jobs(created_at DESC);

-- SC-040: elapsed time tracking
ALTER TABLE async_jobs ADD COLUMN IF NOT EXISTS elapsed_sec FLOAT;
