import httpx
from prefect import get_run_logger, task

from config.settings import settings


@task(
    name="extract-jobs",
    retries=settings.retry_attempts,
    retry_delay_seconds=settings.retry_delay_seconds,
)
def extract_jobs(since_slug: str | None = None) -> list[dict]:
    """
    Fetches job listings from the Arbeitnow public API with pagination.

    If since_slug is provided (incremental mode), pagination stops as soon as
    that slug is encountered — avoids re-fetching already-ingested jobs.
    """
    logger = get_run_logger()
    all_jobs: list[dict] = []

    with httpx.Client(timeout=30.0) as client:
        for page in range(1, settings.max_pages + 1):
            resp = client.get(settings.arbeitnow_base_url, params={"page": page})
            resp.raise_for_status()
            data = resp.json()
            jobs: list[dict] = data.get("data", [])

            if not jobs:
                logger.info(f"No jobs on page {page} — stopping pagination")
                break

            if since_slug:
                new_jobs = []
                reached_known = False
                for job in jobs:
                    if job["slug"] == since_slug:
                        reached_known = True
                        break
                    new_jobs.append(job)
                all_jobs.extend(new_jobs)
                if reached_known:
                    logger.info(
                        f"Reached known slug '{since_slug}' on page {page} — stopping early"
                    )
                    break
            else:
                all_jobs.extend(jobs)

            if not data.get("links", {}).get("next"):
                logger.info(f"No next page after page {page} — stopping pagination")
                break

    logger.info(f"Extracted {len(all_jobs)} jobs from Arbeitnow")
    return all_jobs
