-- Gold layer: daily aggregated analytics
-- Run after silver_schema.sql

CREATE TABLE IF NOT EXISTS job_market_summary (
    id             BIGSERIAL   PRIMARY KEY,
    summary_date   DATE        NOT NULL UNIQUE,
    job_count      INTEGER     NOT NULL,
    remote_count   INTEGER     NOT NULL,
    remote_ratio   NUMERIC(5,2),              -- percentage 0.00–100.00
    avg_salary_min NUMERIC(12,2),
    avg_salary_max NUMERIC(12,2),
    top_tech_stack JSONB,                     -- [{"tech": "Python", "count": 42}, ...]
    refreshed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_market_summary_date ON job_market_summary (summary_date DESC);
