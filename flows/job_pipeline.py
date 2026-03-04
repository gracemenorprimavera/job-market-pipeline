from prefect import flow, get_run_logger

from tasks.extract_jobs import extract_jobs
from tasks.load_supabase import (
    get_latest_slug,
    load_raw_jobs,
    load_clean_jobs,
    build_analytics_table,
    quality_check_bronze,
    quality_check_silver,
)
from tasks.transform_jobs import transform_jobs
from tasks.notify import get_gold_summary, create_pipeline_artifact, send_summary_email


@flow(
    name="job-market-pipeline",
    description="Daily ELT pipeline: Arbeitnow → Supabase bronze / silver / gold",
)
def job_pipeline(full_refresh: bool = False) -> None:
    logger = get_run_logger()
    logger.info(f"Pipeline starting — full_refresh={full_refresh}")

    # --- INCREMENTAL LOAD ---
    since_slug = None if full_refresh else get_latest_slug()

    # --- EXTRACT ---
    raw_jobs = extract_jobs(since_slug=since_slug)

    # --- BRONZE QUALITY CHECK ---
    dq_bronze = quality_check_bronze(raw_jobs)

    # --- BRONZE LOAD ---
    bronze_count = load_raw_jobs(raw_jobs)

    if bronze_count == 0:
        logger.info("No new jobs — skipping silver and gold update")
        return

    # --- TRANSFORM (bronze → silver) ---
    clean_jobs = transform_jobs(raw_jobs)

    # --- SILVER QUALITY CHECK ---
    dq_silver = quality_check_silver(clean_jobs)

    # --- SILVER LOAD ---
    silver_count = load_clean_jobs(clean_jobs)

    # --- GOLD REFRESH (SQL runs inside Supabase) ---
    build_analytics_table()

    # --- SUMMARY: artifact + email ---
    gold_rows = get_gold_summary()
    create_pipeline_artifact(dq_bronze, bronze_count, dq_silver, silver_count, gold_rows)
    send_summary_email(dq_bronze, bronze_count, dq_silver, silver_count, gold_rows)

    logger.info("Pipeline complete")


if __name__ == "__main__":
    # Local development: run a full refresh to populate all three layers
    job_pipeline(full_refresh=True)
