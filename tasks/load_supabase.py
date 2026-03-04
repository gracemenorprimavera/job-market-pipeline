import json
from datetime import datetime, timezone

from prefect import task, get_run_logger
from supabase import create_client, Client

from config.settings import settings


def get_supabase() -> Client:
    """Returns a Supabase client using the service_role key (full access)."""
    return create_client(settings.supabase_url, settings.supabase_service_key)


# ---------------------------------------------------------------------------
# Incremental load helper
# ---------------------------------------------------------------------------

@task(name="get-latest-slug")
def get_latest_slug() -> str | None:
    """Returns the slug of the most recently ingested job for incremental loading."""
    client = get_supabase()
    result = (
        client.table("jobs_raw")
        .select("slug")
        .order("ingested_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data
    slug = rows[0]["slug"] if rows else None
    get_run_logger().info(f"Latest ingested slug: {slug}")
    return slug


# ---------------------------------------------------------------------------
# Bronze
# ---------------------------------------------------------------------------

@task(name="quality-check-bronze")
def quality_check_bronze(jobs: list[dict]) -> dict:
    """Returns a stats dict so callers can include results in artifacts/emails."""
    logger = get_run_logger()
    null_company   = sum(1 for j in jobs if not j.get("company_name"))
    slugs          = [j["slug"] for j in jobs]
    duplicate_slugs = len(slugs) - len(set(slugs))

    if len(jobs) == 0:
        logger.warning("DQ WARN: 0 jobs extracted — API may be down or no new jobs")
    if null_company > 0:
        logger.warning(f"DQ WARN: {null_company} jobs have no company name")
    if duplicate_slugs > 0:
        logger.warning(f"DQ WARN: {duplicate_slugs} duplicate slugs in extracted batch")

    logger.info(
        f"DQ Bronze: {len(jobs)} jobs | "
        f"{null_company} null companies | "
        f"{duplicate_slugs} duplicate slugs"
    )
    return {"total": len(jobs), "null_companies": null_company, "duplicate_slugs": duplicate_slugs}


@task(name="load-raw-jobs")
def load_raw_jobs(jobs: list[dict]) -> int:
    """Batch upserts raw jobs into jobs_raw. Returns number of rows processed."""
    logger = get_run_logger()
    if not jobs:
        logger.warning("No jobs to load into bronze layer")
        return 0

    client = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    rows = [
        {
            "slug":        job["slug"],
            "title":       job.get("title"),
            "company":     job.get("company_name"),
            "location":    job.get("location"),
            "remote":      job.get("remote", False),
            "tags":        job.get("tags") or [],
            "job_types":   job.get("job_types") or [],
            "url":         job.get("url"),
            "description": job.get("description"),
            "raw_json":    json.dumps(job),
            "ingested_at": now,
        }
        for job in jobs
    ]

    # Deduplicate by slug — the API occasionally returns the same job on multiple pages.
    # PostgreSQL raises an error if a single upsert batch targets the same row twice.
    rows = list({row["slug"]: row for row in rows}.values())

    total = 0
    for i in range(0, len(rows), settings.batch_size):
        batch = rows[i : i + settings.batch_size]
        client.table("jobs_raw").upsert(batch, on_conflict="slug").execute()
        total += len(batch)
        logger.info(f"Bronze upsert: {total}/{len(rows)} rows")

    logger.info(f"Finished loading {total} rows into jobs_raw")
    return total


# ---------------------------------------------------------------------------
# Silver
# ---------------------------------------------------------------------------

@task(name="quality-check-silver")
def quality_check_silver(jobs: list[dict]) -> dict:
    """Returns a stats dict so callers can include results in artifacts/emails."""
    logger = get_run_logger()
    null_company = sum(1 for j in jobs if not j.get("company") or j["company"] == "Unknown")
    null_date    = sum(1 for j in jobs if not j.get("posted_date"))

    if null_company > len(jobs) * 0.1:
        logger.warning(
            f"DQ WARN: {null_company}/{len(jobs)} silver records have no company (>10%)"
        )
    if null_date > len(jobs) * 0.2:
        logger.warning(
            f"DQ WARN: {null_date}/{len(jobs)} silver records have no posted_date (>20%)"
        )

    logger.info(
        f"DQ Silver: {len(jobs)} records | "
        f"{null_company} unknown companies | "
        f"{null_date} null dates"
    )
    return {"total": len(jobs), "null_companies": null_company, "null_dates": null_date}


@task(name="load-clean-jobs")
def load_clean_jobs(jobs: list[dict]) -> int:
    """Batch upserts cleaned jobs into jobs_clean. Returns number of rows processed."""
    logger = get_run_logger()
    if not jobs:
        logger.warning("No jobs to load into silver layer")
        return 0

    client = get_supabase()
    # Deduplicate by slug for the same reason as bronze
    jobs = list({job["slug"]: job for job in jobs}.values())
    total = 0
    for i in range(0, len(jobs), settings.batch_size):
        batch = jobs[i : i + settings.batch_size]
        client.table("jobs_clean").upsert(batch, on_conflict="slug").execute()
        total += len(batch)
        logger.info(f"Silver upsert: {total}/{len(jobs)} rows")

    logger.info(f"Finished loading {total} rows into jobs_clean")
    return total


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------

@task(name="build-analytics-table")
def build_analytics_table() -> None:
    """Triggers the refresh_gold() SQL function inside Supabase."""
    logger = get_run_logger()
    client = get_supabase()
    client.rpc("refresh_gold").execute()
    logger.info("Gold analytics table refreshed via refresh_gold()")
