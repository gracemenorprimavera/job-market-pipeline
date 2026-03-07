from prefect import task, get_run_logger


@task(name="aggregate-jobs")
def aggregate_jobs(jobs: list[dict]) -> dict:
    """
    Placeholder for Prefect aggregation tasks.

    TODO: Implement the following aggregations:
    - Tech stack frequency (count occurrences of each technology)
    - Job counts by country and city
    - Remote vs on-site distribution
    - Job type distribution (full-time, part-time, contract, etc.)
    """
    logger = get_run_logger()
    logger.info("aggregate_jobs task is not yet implemented")
    return {}
