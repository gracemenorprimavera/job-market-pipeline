-- Bronze layer: raw API responses
-- Run this first

CREATE TABLE IF NOT EXISTS jobs_raw (
    id          BIGSERIAL   PRIMARY KEY,
    slug        TEXT        NOT NULL UNIQUE,   -- Arbeitnow unique job identifier
    title       TEXT,
    company     TEXT,
    location    TEXT,
    remote      BOOLEAN,
    tags        TEXT[],                        -- raw technology/skill tags from API
    job_types   TEXT[],                        -- e.g. ["full-time", "contract"]
    url         TEXT,
    description TEXT,
    raw_json    JSONB       NOT NULL,          -- full API response object (for replayability)
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_raw_slug        ON jobs_raw (slug);
CREATE INDEX IF NOT EXISTS idx_jobs_raw_ingested_at ON jobs_raw (ingested_at DESC);
