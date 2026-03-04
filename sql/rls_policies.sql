-- Row Level Security policies
-- Run last, after all tables and the gold function exist

-- Enable RLS on all three tables
ALTER TABLE jobs_raw           ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs_clean         ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_market_summary ENABLE ROW LEVEL SECURITY;

-- Pipeline uses the service_role key which bypasses RLS automatically.
-- No policy needed for the pipeline.

-- Dashboard uses the anon key: read-only access to silver and gold only.
CREATE POLICY anon_read_jobs_clean ON jobs_clean
    FOR SELECT TO anon USING (true);

CREATE POLICY anon_read_summary ON job_market_summary
    FOR SELECT TO anon USING (true);

-- Bronze (jobs_raw) is intentionally private.
-- No anon policy = anon key returns empty results (not an error).
