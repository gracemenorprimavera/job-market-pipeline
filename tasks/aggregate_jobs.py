from prefect import task, get_run_logger


@task(name="aggregate-jobs")
def aggregate_jobs(silver_jobs: list[dict]) -> dict:
    """
    Placeholder for aggregation tasks.

    TODO: Implement aggregations over silver-layer job records, e.g.:
      - Top tech stacks by frequency
      - Job counts by country / city
      - Remote vs on-site breakdown
      - Job type distribution
    """
    logger = get_run_logger()
    logger.info("aggregate_jobs task is not yet implemented")
    return {}
