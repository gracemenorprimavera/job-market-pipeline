-- Silver layer: cleaned and normalised job data
-- Run after bronze_schema.sql

CREATE TABLE IF NOT EXISTS jobs_clean (
    id           BIGSERIAL   PRIMARY KEY,
    slug         TEXT        NOT NULL UNIQUE,
    title        TEXT,
    company      TEXT        NOT NULL,
    country      TEXT,
    city         TEXT,
    remote       BOOLEAN,
    tech_stack   TEXT[],                       -- normalised from raw tags
    job_types    TEXT[],
    salary_min   NUMERIC(12,2),
    salary_max   NUMERIC(12,2),
    currency     TEXT,
    posted_date  DATE,
    source_url   TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_clean_slug        ON jobs_clean (slug);
CREATE INDEX IF NOT EXISTS idx_jobs_clean_posted_date ON jobs_clean (posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_clean_country     ON jobs_clean (country);
CREATE INDEX IF NOT EXISTS idx_jobs_clean_remote      ON jobs_clean (remote);
