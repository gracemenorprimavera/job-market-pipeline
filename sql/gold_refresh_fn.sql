-- Gold refresh function: aggregates jobs_clean → job_market_summary
-- Called by the pipeline via supabase.rpc("refresh_gold")
-- Idempotent: safe to run on every pipeline execution
-- Run after gold_schema.sql

CREATE OR REPLACE FUNCTION refresh_gold()
RETURNS void
LANGUAGE sql
SECURITY DEFINER
AS $$
    INSERT INTO job_market_summary (
        summary_date,
        job_count,
        remote_count,
        remote_ratio,
        avg_salary_min,
        avg_salary_max,
        top_tech_stack,
        refreshed_at
    )
    SELECT
        posted_date                                                           AS summary_date,
        COUNT(*)                                                              AS job_count,
        COUNT(*) FILTER (WHERE remote = true)                                 AS remote_count,
        ROUND(COUNT(*) FILTER (WHERE remote = true) * 100.0 / COUNT(*), 2)   AS remote_ratio,
        ROUND(AVG(salary_min), 2)                                             AS avg_salary_min,
        ROUND(AVG(salary_max), 2)                                             AS avg_salary_max,
        (
            SELECT jsonb_agg(row_to_json(t))
            FROM (
                SELECT unnested_tech AS tech, COUNT(*) AS count
                FROM jobs_clean jc2
                CROSS JOIN LATERAL unnest(jc2.tech_stack) AS unnested_tech
                WHERE jc2.posted_date = jc.posted_date
                  AND unnested_tech <> ''
                GROUP BY unnested_tech
                ORDER BY count DESC
                LIMIT 10
            ) t
        )                                                                     AS top_tech_stack,
        NOW()                                                                 AS refreshed_at
    FROM jobs_clean jc
    WHERE posted_date IS NOT NULL
    GROUP BY posted_date
    ON CONFLICT (summary_date) DO UPDATE SET
        job_count      = EXCLUDED.job_count,
        remote_count   = EXCLUDED.remote_count,
        remote_ratio   = EXCLUDED.remote_ratio,
        avg_salary_min = EXCLUDED.avg_salary_min,
        avg_salary_max = EXCLUDED.avg_salary_max,
        top_tech_stack = EXCLUDED.top_tech_stack,
        refreshed_at   = NOW();
$$;
