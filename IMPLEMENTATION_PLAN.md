# Job Market Pipeline — Implementation Plan

> **API**: Arbeitnow (free, no auth required)
> **Orchestration**: Prefect Cloud + Managed Work Pool (no local worker)
> **Database**: Supabase PostgreSQL (new project, free tier)
> **Dashboard**: Lovable (AI-generated)
> **Language**: Python with `uv`

---

## Project Structure

```
job-market-pipeline/
├── pyproject.toml
├── prefect.yaml
├── .env                         # secrets — never commit
├── .env.example                 # template — commit this
├── .gitignore
├── README.md
├── flows/
│   └── job_pipeline.py          # Main Prefect flow (entry point)
├── tasks/
│   ├── extract_jobs.py          # Arbeitnow API extraction
│   ├── load_supabase.py         # Bronze + silver upserts, gold trigger
│   └── transform_jobs.py        # Silver cleaning and normalization
├── sql/
│   ├── bronze_schema.sql        # jobs_raw table + indexes
│   ├── silver_schema.sql        # jobs_clean table + indexes
│   ├── gold_schema.sql          # job_market_summary table + indexes
│   ├── gold_refresh_fn.sql      # PostgreSQL function: refresh_gold()
│   ├── rls_policies.sql         # Row Level Security policies
│   └── dashboard_views.sql      # Read-optimized views for dashboard
├── config/
│   └── settings.py              # Pydantic-settings env config
└── deployment/
    └── deploy.py                # One-time Prefect Cloud registration script
```

---

## Phase 0: Setup & Prerequisites

### Goals
- Initialize the Python project with `uv`
- Create and configure Supabase and Prefect Cloud accounts
- Set up environment variables

### 0.1 Python Project Initialization

```bash
cd job-market-pipeline
uv init --no-readme
uv add prefect supabase pydantic-settings httpx
uv add --dev pytest
```

**Dependencies:**
- `prefect` — flow orchestration and scheduling
- `supabase` — Python client wrapping Supabase's PostgREST API
- `pydantic-settings` — typed, validated environment variable loading
- `httpx` — HTTP client for Arbeitnow API (supports timeouts cleanly)

### 0.2 Supabase Project Creation

1. Login using my personal account at [supabase.com](https://supabase.com)
2. Create a new project — choose **Free tier** (500 MB storage, 2 GB bandwidth — sufficient for this pipeline)
3. From **Project Settings > API**, note:
   - `SUPABASE_URL` — Project URL
   - `SUPABASE_ANON_KEY` — public key (read-only, used by dashboard only)
   - `SUPABASE_SERVICE_KEY` — service_role key (full access, used by pipeline only)

### 0.3 Prefect Cloud Setup

1. Login using my personal account at [app.prefect.io](https://app.prefect.io) (free tier)
2. Create a **Workspace**
3. Create a **Managed Work Pool**:
   - Navigate to Work Pools → Create Work Pool
   - Type: **Prefect Managed**
   - Name: `default-work-pool`
4. Note your **Prefect API Key** from Settings → API Keys
5. Authenticate locally:
   ```bash
   prefect cloud login --key <API_KEY>
   prefect cloud workspace set --workspace <your-workspace-slug>
   ```

### 0.4 GitHub Repository

The Prefect Managed Work Pool pulls flow code from GitHub at runtime:

1. Create a public GitHub repo (e.g., `job-market-pipeline`)
2. Push the project to `main`
3. The `prefect.yaml` deployment config will reference this repo

### 0.5 Environment Variables

**`.env`** (never commit — add to `.gitignore`):
```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>
PREFECT_API_KEY=<prefect_api_key>
PREFECT_API_URL=https://api.prefect.cloud/api/accounts/<account-id>/workspaces/<workspace-id>
```

**`.env.example`** (commit this):
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
PREFECT_API_KEY=
PREFECT_API_URL=
```

**`.gitignore`**:
```
.env
.venv/
__pycache__/
*.pyc
```

### Validation
- `uv run python -c "import prefect, supabase; print('OK')"` passes
- Supabase project status is **Active**
- `prefect cloud workspace ls` shows your workspace

---

## Phase 1: Database Schema

### Goals
- Create all three medallion-layer tables in Supabase
- Add indexes for query performance
- Configure Row Level Security (RLS) for secure dashboard access

### 1.1 Bronze — `sql/bronze_schema.sql`

```sql
CREATE TABLE IF NOT EXISTS jobs_raw (
    id            BIGSERIAL   PRIMARY KEY,
    slug          TEXT        NOT NULL UNIQUE,   -- Arbeitnow's unique job identifier
    title         TEXT,
    company       TEXT,
    location      TEXT,
    remote        BOOLEAN,
    tags          TEXT[],                        -- raw technology/skill tags
    job_types     TEXT[],                        -- e.g. ["full-time", "contract"]
    url           TEXT,
    description   TEXT,
    raw_json      JSONB       NOT NULL,          -- full API response for replayability
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_raw_slug        ON jobs_raw (slug);
CREATE INDEX IF NOT EXISTS idx_jobs_raw_ingested_at ON jobs_raw (ingested_at DESC);
```

**Design notes:**
- `slug` is Arbeitnow's natural unique key — used for upsert conflict detection and incremental loading
- `raw_json` stores the complete API response so we can re-derive silver/gold without re-calling the API
- `TEXT[]` for `tags` enables efficient PostgreSQL array operations (e.g., `ANY`, `unnest`)
- `ingested_at DESC` index supports the incremental load query (`SELECT slug ORDER BY ingested_at DESC LIMIT 1`)

### 1.2 Silver — `sql/silver_schema.sql`

```sql
CREATE TABLE IF NOT EXISTS jobs_clean (
    id            BIGSERIAL   PRIMARY KEY,
    slug          TEXT        NOT NULL UNIQUE,
    title         TEXT,
    company       TEXT        NOT NULL,
    country       TEXT,
    city          TEXT,
    remote        BOOLEAN,
    tech_stack    TEXT[],                        -- normalized from raw tags
    job_types     TEXT[],
    salary_min    NUMERIC(12,2),
    salary_max    NUMERIC(12,2),
    currency      TEXT,
    posted_date   DATE,
    source_url    TEXT,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_clean_slug        ON jobs_clean (slug);
CREATE INDEX IF NOT EXISTS idx_jobs_clean_posted_date ON jobs_clean (posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_clean_country     ON jobs_clean (country);
CREATE INDEX IF NOT EXISTS idx_jobs_clean_remote      ON jobs_clean (remote);
```

### 1.3 Gold — `sql/gold_schema.sql`

```sql
CREATE TABLE IF NOT EXISTS job_market_summary (
    id              BIGSERIAL   PRIMARY KEY,
    summary_date    DATE        NOT NULL UNIQUE,
    job_count       INTEGER     NOT NULL,
    remote_count    INTEGER     NOT NULL,
    remote_ratio    NUMERIC(5,2),               -- percentage (0.00 to 100.00)
    avg_salary_min  NUMERIC(12,2),
    avg_salary_max  NUMERIC(12,2),
    top_tech_stack  JSONB,                      -- [{"tech": "Python", "count": 42}, ...]
    refreshed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_market_summary_date ON job_market_summary (summary_date DESC);
```

**Why JSONB for `top_tech_stack`**: avoids a separate tech_counts join table at the gold layer; the dashboard reads it directly as a JSON array. The array is capped at 10 entries per day in the aggregation SQL.

### 1.4 Gold Refresh Function — `sql/gold_refresh_fn.sql`

Rather than sending raw SQL through the API (which PostgREST doesn't support), create a PostgreSQL function the pipeline calls via `supabase.rpc()`:

```sql
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
        posted_date                                                       AS summary_date,
        COUNT(*)                                                          AS job_count,
        COUNT(*) FILTER (WHERE remote = true)                             AS remote_count,
        ROUND(COUNT(*) FILTER (WHERE remote = true) * 100.0 / COUNT(*), 2) AS remote_ratio,
        ROUND(AVG(salary_min), 2)                                         AS avg_salary_min,
        ROUND(AVG(salary_max), 2)                                         AS avg_salary_max,
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
        )                                                                 AS top_tech_stack,
        NOW()                                                             AS refreshed_at
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
```

`ON CONFLICT DO UPDATE` makes this idempotent — safe to call on every pipeline run. Existing rows are refreshed in place.

### 1.5 Row Level Security — `sql/rls_policies.sql`

```sql
-- Enable RLS on all tables
ALTER TABLE jobs_raw           ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs_clean         ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_market_summary ENABLE ROW LEVEL SECURITY;

-- Service role (pipeline) bypasses RLS automatically — no policy needed

-- Dashboard (anon key) gets read-only access to silver and gold
CREATE POLICY anon_read_jobs_clean ON jobs_clean
    FOR SELECT TO anon USING (true);

CREATE POLICY anon_read_summary ON job_market_summary
    FOR SELECT TO anon USING (true);

-- Bronze (jobs_raw) is intentionally private — no anon policy = no access
```

### 1.6 SQL Execution Order in Supabase SQL Editor

Run in this order:
1. `bronze_schema.sql`
2. `silver_schema.sql`
3. `gold_schema.sql`
4. `gold_refresh_fn.sql`
5. `rls_policies.sql`

### Validation
- All three tables visible in Supabase Table Editor
- Indexes visible in Database → Indexes
- `refresh_gold` function visible in Database → Functions
- Anon key can SELECT from `jobs_clean` and `job_market_summary`
- Anon key receives empty results (not an error) from `jobs_raw` — RLS is blocking correctly

---

## Phase 2: Configuration

### Goals
- Centralize all environment-driven configuration
- Provide a single source of truth for tunable parameters

### `config/settings.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str

    # Arbeitnow API
    arbeitnow_base_url: str = "https://www.arbeitnow.com/api/job-board-api"

    # Pipeline tuning (adjustable without code changes)
    batch_size: int = 200      # records per upsert batch (stay under PostgREST 1MB limit)
    max_pages: int = 10        # API pages per run (10 pages ≈ 1,000 jobs max)
    retry_attempts: int = 3
    retry_delay_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
```

**Why Pydantic-settings**: validates that required vars are present at startup, provides typed access, and reads from both `.env` files (local) and real environment variables (Prefect Cloud runtime) with no code change.

---

## Phase 3: Extract & Bronze Load

### Goals
- Fetch jobs from Arbeitnow with pagination and retries
- Implement incremental loading — only fetch jobs newer than the last run
- Batch upsert raw records into `jobs_raw`
- Run data quality checks on extracted data

### 3.1 `tasks/extract_jobs.py`

```python
import httpx
from prefect import task, get_run_logger
from config.settings import settings


@task(
    name="extract-jobs",
    retries=settings.retry_attempts,
    retry_delay_seconds=settings.retry_delay_seconds,
)
def extract_jobs(since_slug: str | None = None) -> list[dict]:
    """
    Fetches job listings from Arbeitnow with pagination.

    If since_slug is set (incremental mode), pagination stops as soon as
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
                    logger.info(f"Reached known slug '{since_slug}' — stopping early at page {page}")
                    break
            else:
                all_jobs.extend(jobs)

            if not data.get("links", {}).get("next"):
                break

    logger.info(f"Extracted {len(all_jobs)} jobs from Arbeitnow")
    return all_jobs
```

**Why `since_slug` instead of `since_date`**: Arbeitnow returns jobs sorted newest-first. Matching on a known slug is exact and avoids timezone ambiguity in date comparisons.

### 3.2 `tasks/load_supabase.py` — Supabase client + Bronze tasks

```python
import json
from datetime import datetime, timezone
from prefect import task, get_run_logger
from supabase import create_client, Client
from config.settings import settings


def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


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
    return rows[0]["slug"] if rows else None


@task(name="quality-check-bronze")
def quality_check_bronze(jobs: list[dict]) -> None:
    logger = get_run_logger()

    if len(jobs) == 0:
        logger.warning("DQ WARN: 0 jobs extracted — API may be down or rate-limited")
        return

    null_company = sum(1 for j in jobs if not j.get("company_name"))
    slugs = [j["slug"] for j in jobs]
    duplicate_slugs = len(slugs) - len(set(slugs))

    if null_company > 0:
        logger.warning(f"DQ WARN: {null_company} jobs have no company name")
    if duplicate_slugs > 0:
        logger.warning(f"DQ WARN: {duplicate_slugs} duplicate slugs in extracted batch")

    logger.info(f"DQ Bronze PASS: {len(jobs)} jobs, {null_company} null companies, {duplicate_slugs} duplicate slugs")


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
            "tags":        job.get("tags", []),
            "job_types":   job.get("job_types", []),
            "url":         job.get("url"),
            "description": job.get("description"),
            "raw_json":    json.dumps(job),
            "ingested_at": now,
        }
        for job in jobs
    ]

    total = 0
    for i in range(0, len(rows), settings.batch_size):
        batch = rows[i : i + settings.batch_size]
        client.table("jobs_raw").upsert(batch, on_conflict="slug").execute()
        total += len(batch)
        logger.info(f"Bronze upsert progress: {total}/{len(rows)} rows")

    logger.info(f"Total rows upserted to jobs_raw: {total}")
    return total
```

**Why batch upsert**: Supabase's PostgREST has a ~1 MB default request size limit. At `batch_size=200`, each batch is well under that ceiling while minimizing network round trips compared to row-by-row inserts.

---

## Phase 4: Silver Transformation

### Goals
- Clean and normalize bronze data in Python
- Normalize tech tags (aliases → canonical names)
- Parse `location` string into structured `city` / `country`
- Upsert into `jobs_clean` in batches
- Run silver data quality checks

**Design decision**: Silver runs in Python (not SQL) because tag normalization and location parsing require string-matching logic that is more maintainable and testable in Python than in PostgreSQL.

### 4.1 `tasks/transform_jobs.py`

```python
import re
from datetime import datetime, timezone
from prefect import task, get_run_logger
from config.settings import settings


# Maps common variants to a canonical tech name — extend freely
TECH_ALIASES: dict[str, str] = {
    "react.js": "React",    "reactjs": "React",
    "node.js": "Node.js",   "nodejs": "Node.js",
    "vue.js": "Vue",        "vuejs": "Vue",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "ml": "Machine Learning",
    "ai": "AI",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "ts": "TypeScript",
    "js": "JavaScript",
}

# Lower-cased country names to detect in location strings — extend freely
KNOWN_COUNTRIES = [
    "united states", "usa", "us",
    "united kingdom", "uk",
    "germany", "deutschland",
    "canada", "france", "netherlands",
    "australia", "india", "spain",
    "remote", "worldwide", "anywhere",
]


def normalize_tech_tag(tag: str) -> str:
    return TECH_ALIASES.get(tag.lower().strip(), tag.strip())


def parse_location(location: str | None) -> tuple[str | None, str | None]:
    """Returns (city, country) parsed from a free-text location string."""
    if not location:
        return None, None
    lower = location.lower()
    for country in KNOWN_COUNTRIES:
        if country in lower:
            # Everything before the country name is treated as city
            parts = re.split(rf"\s*[,/]?\s*{re.escape(country)}", lower, maxsplit=1)
            city = parts[0].strip().title() if parts[0].strip() else None
            return city, country.title()
    # No known country matched — treat the whole string as the city
    return location.strip().title(), None


@task(name="transform-jobs")
def transform_jobs(raw_jobs: list[dict]) -> list[dict]:
    """Cleans and normalizes bronze records into silver-ready dicts."""
    logger = get_run_logger()
    now = datetime.now(timezone.utc).isoformat()
    cleaned = []

    for job in raw_jobs:
        tags = job.get("tags") or []
        tech_stack = [normalize_tech_tag(t) for t in tags]
        tech_stack = list(dict.fromkeys(tech_stack))  # dedupe, preserve order

        city, country = parse_location(job.get("location"))

        # Arbeitnow's public endpoint does not expose structured salary fields;
        # salary_min/max remain NULL. Extend here if a future API version adds them.
        cleaned.append({
            "slug":         job["slug"],
            "title":        job.get("title"),
            "company":      job.get("company_name") or "Unknown",
            "country":      country,
            "city":         city,
            "remote":       job.get("remote", False),
            "tech_stack":   tech_stack,
            "job_types":    job.get("job_types", []),
            "salary_min":   None,
            "salary_max":   None,
            "currency":     None,
            "posted_date":  (job.get("created_at") or "")[:10] or None,  # "YYYY-MM-DD"
            "source_url":   job.get("url"),
            "processed_at": now,
        })

    logger.info(f"Transformed {len(cleaned)} jobs for silver layer")
    return cleaned
```

### 4.2 Silver Load + Quality Check (in `tasks/load_supabase.py`)

```python
@task(name="quality-check-silver")
def quality_check_silver(jobs: list[dict]) -> None:
    logger = get_run_logger()
    null_company = sum(1 for j in jobs if not j.get("company") or j["company"] == "Unknown")
    null_date    = sum(1 for j in jobs if not j.get("posted_date"))

    if null_company > len(jobs) * 0.1:
        logger.warning(f"DQ WARN: {null_company}/{len(jobs)} silver records have no company (>10%)")
    if null_date > len(jobs) * 0.2:
        logger.warning(f"DQ WARN: {null_date}/{len(jobs)} silver records have no posted_date (>20%)")

    logger.info(f"DQ Silver: {len(jobs)} records, {null_company} unknown companies, {null_date} null dates")


@task(name="load-clean-jobs")
def load_clean_jobs(jobs: list[dict]) -> int:
    logger = get_run_logger()
    if not jobs:
        logger.warning("No jobs to load into silver layer")
        return 0

    client = get_supabase()
    total = 0
    for i in range(0, len(jobs), settings.batch_size):
        batch = jobs[i : i + settings.batch_size]
        client.table("jobs_clean").upsert(batch, on_conflict="slug").execute()
        total += len(batch)
        logger.info(f"Silver upsert progress: {total}/{len(jobs)} rows")

    logger.info(f"Total rows upserted to jobs_clean: {total}")
    return total
```

---

## Phase 5: Gold Analytics

**Design decision**: Gold aggregation runs entirely as SQL inside Supabase via `supabase.rpc("refresh_gold")`. This means:
- Zero data transfer from Supabase to Python for aggregation
- PostgreSQL handles `GROUP BY`, `unnest`, and JSONB construction natively
- The function is idempotent (`ON CONFLICT DO UPDATE`) — safe to call on every run

The SQL was defined in Phase 1 (`gold_refresh_fn.sql`). The Python task is a thin wrapper:

### Gold Trigger Task (in `tasks/load_supabase.py`)

```python
@task(name="build-analytics-table")
def build_analytics_table() -> None:
    logger = get_run_logger()
    client = get_supabase()
    client.rpc("refresh_gold").execute()
    logger.info("Gold analytics table refreshed via refresh_gold()")
```

---

## Phase 6: Prefect Flow Composition

### Goals
- Compose all tasks into one Prefect flow
- Wire incremental loading logic via `since_slug`
- Early-exit when there are no new jobs (avoids unnecessary silver/gold refresh)
- Support `full_refresh` parameter for manual resets or the first run

### `flows/job_pipeline.py`

```python
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


@flow(
    name="job-market-pipeline",
    description="Daily ELT pipeline: Arbeitnow → Supabase bronze / silver / gold",
)
def job_pipeline(full_refresh: bool = False) -> None:
    logger = get_run_logger()
    logger.info(f"Pipeline starting — full_refresh={full_refresh}")

    # INCREMENTAL LOAD: get the most recently ingested slug
    since_slug = None if full_refresh else get_latest_slug()

    # EXTRACT
    raw_jobs = extract_jobs(since_slug=since_slug)

    # BRONZE QUALITY CHECK
    quality_check_bronze(raw_jobs)

    # BRONZE LOAD
    bronze_count = load_raw_jobs(raw_jobs)

    if bronze_count == 0:
        logger.info("No new jobs found — skipping silver and gold update")
        return

    # TRANSFORM
    clean_jobs = transform_jobs(raw_jobs)

    # SILVER QUALITY CHECK
    quality_check_silver(clean_jobs)

    # SILVER LOAD
    load_clean_jobs(clean_jobs)

    # GOLD REFRESH (SQL, runs inside Supabase)
    build_analytics_table()

    logger.info("Pipeline complete")


if __name__ == "__main__":
    # For local development: run a full refresh
    job_pipeline(full_refresh=True)
```

### Flow Execution Order

```
get_latest_slug()
    ↓
extract_jobs(since_slug)
    ↓
quality_check_bronze()
    ↓
load_raw_jobs()  ← early exit here if 0 new jobs
    ↓
transform_jobs()
    ↓
quality_check_silver()
    ↓
load_clean_jobs()
    ↓
build_analytics_table()  ← SQL runs inside Supabase
```

Tasks are sequential (each output feeds the next) — no false parallelism.

---

## Phase 7: Prefect Cloud Deployment

### Goals
- Deploy the flow to Prefect Cloud using the managed work pool
- Store Supabase credentials as Prefect secrets (not in env files on managed infra)
- Configure a daily schedule
- Register the deployment once and let Prefect Cloud handle execution

### 7.1 Prefect Secrets

Store credentials in Prefect Cloud — not in any file on managed infrastructure:

```bash
prefect secret set SUPABASE_URL
prefect secret set SUPABASE_SERVICE_KEY
```

These are injected as environment variables at runtime. `pydantic-settings` in `config/settings.py` reads them identically to `.env` file values.

### 7.2 `prefect.yaml`

```yaml
name: job-market-pipeline
prefect-version: "3.x"

# No build/push steps — managed work pool handles this
build: null
push: null

pull:
  - prefect.deployments.steps.git_clone:
      repository: https://github.com/<your-username>/job-market-pipeline.git
      branch: main

deployments:
  - name: daily-job-pipeline
    version: "1.0.0"
    tags: ["job-market", "elt", "daily"]
    description: "Daily Arbeitnow → Supabase ELT pipeline"

    entrypoint: flows/job_pipeline.py:job_pipeline

    work_pool:
      name: default-work-pool           # Prefect Managed work pool created in Phase 0
      job_variables:
        pip_packages:
          - "supabase"
          - "pydantic-settings"
          - "httpx"
        env:
          SUPABASE_URL: "{{ prefect.secrets.SUPABASE_URL }}"
          SUPABASE_SERVICE_KEY: "{{ prefect.secrets.SUPABASE_SERVICE_KEY }}"

    parameters:
      full_refresh: false              # default: incremental

    schedules:
      - cron: "0 6 * * *"             # daily at 06:00 UTC
        timezone: "UTC"
        active: true
```

### 7.3 `deployment/deploy.py`

```python
"""Run once to register the deployment with Prefect Cloud."""
import subprocess
from pathlib import Path

subprocess.run(
    ["prefect", "deploy", "--all"],
    check=True,
    cwd=str(Path(__file__).parent.parent),
)
```

Or run directly:
```bash
prefect deploy --all
```

### 7.4 First Full Run

After deployment, trigger a manual full run to populate all three layers:

```bash
prefect deployment run 'job-market-pipeline/daily-job-pipeline' --param full_refresh=true
```

### Validation
- Deployment visible in Prefect Cloud UI under **Deployments**
- All tasks show green on the first run
- Supabase Table Editor shows data in `jobs_raw`, `jobs_clean`, `job_market_summary`
- Next scheduled run visible in Prefect Cloud under **Schedules**

---

## Phase 8: Lovable Dashboard

### Goals
- Create read-optimized SQL views for the dashboard to query
- Configure Supabase anon access for the views
- Generate a complete Lovable prompt to produce the dashboard

### 8.1 Dashboard Views — `sql/dashboard_views.sql`

These views aggregate data into exactly the shapes the dashboard needs — no client-side computation required:

```sql
-- KPI cards: single-row summary
CREATE OR REPLACE VIEW dashboard_kpis AS
SELECT
    SUM(job_count)                              AS total_jobs,
    ROUND(AVG(remote_ratio), 1)                 AS avg_remote_ratio,
    ROUND(AVG(avg_salary_min), 0)               AS overall_avg_salary_min,
    ROUND(AVG(avg_salary_max), 0)               AS overall_avg_salary_max,
    MIN(summary_date)                           AS data_from,
    MAX(summary_date)                           AS data_to,
    MAX(refreshed_at)                           AS last_refreshed
FROM job_market_summary;

-- Line chart: jobs and remote count over time
CREATE OR REPLACE VIEW dashboard_jobs_over_time AS
SELECT
    summary_date,
    job_count,
    remote_count
FROM job_market_summary
ORDER BY summary_date ASC;

-- Horizontal bar chart: top technologies across all dates
CREATE OR REPLACE VIEW dashboard_top_tech AS
SELECT
    t.tech,
    SUM(t.count) AS total_count
FROM job_market_summary,
     LATERAL jsonb_to_recordset(top_tech_stack) AS t(tech text, count int)
GROUP BY t.tech
ORDER BY total_count DESC
LIMIT 15;

-- Grant anon read access to views
GRANT SELECT ON dashboard_kpis          TO anon;
GRANT SELECT ON dashboard_jobs_over_time TO anon;
GRANT SELECT ON dashboard_top_tech      TO anon;
```

Run this SQL in Supabase SQL Editor after Phase 7 has populated data.

### 8.2 Lovable Prompt

Paste this into Lovable to generate the dashboard:

```
Build a clean, minimal analytics dashboard called "Job Market Insights".

It reads live data from a Supabase PostgreSQL database using the JavaScript Supabase client.

Supabase credentials (read-only):
- Project URL: <YOUR_SUPABASE_URL>
- Anon Key: <YOUR_SUPABASE_ANON_KEY>

---

LAYOUT: Single page. Header at top. Four KPI stat cards in a 2×2 or 4-column row. Three chart cards below in a single row.

---

KPI CARDS (query from Supabase view "dashboard_kpis" — returns one row):
1. "Total Jobs Listed" — field: total_jobs
2. "Remote Ratio" — field: avg_remote_ratio, display as "XX.X%"
3. "Avg Min Salary" — field: overall_avg_salary_min, display as "$XX,XXX" (show "N/A" if null)
4. "Data Range" — display: data_from + " → " + data_to

---

CHARTS (query from Supabase — one query per chart):

Chart 1: Line chart — "Jobs Posted Over Time"
- Source: view "dashboard_jobs_over_time"
- X-axis: summary_date (formatted as MMM DD)
- Y-axis: job_count
- Add a second line for remote_count in a different color

Chart 2: Horizontal bar chart — "Top Technologies"
- Source: view "dashboard_top_tech"
- Y-axis (labels): tech
- X-axis (values): total_count
- Show top 10 bars
- Highlight the top bar in accent color

Chart 3: Donut chart — "Remote vs Onsite"
- Source: view "dashboard_kpis" field avg_remote_ratio
- Two segments: Remote = avg_remote_ratio%, Onsite = 100 - avg_remote_ratio%
- Show percentages on the chart

---

FOOTER: "Last updated: " + last_refreshed timestamp from dashboard_kpis. Show in muted text.

---

DESIGN:
- Dark theme: background #0f172a (slate-900)
- Cards: #1e293b (slate-800) with 1px border #334155 (slate-700)
- Accent color: #6366f1 (indigo-500)
- Chart lines/bars: indigo for primary, #94a3b8 (slate-400) for secondary
- Font: system sans-serif
- Fully responsive — stack cards vertically on mobile
- Loading skeleton states while data fetches
- Show an error message if Supabase query fails
```

### 8.3 Dashboard Deployment

Lovable auto-hosts the generated app. Use the Lovable-provided URL for the portfolio.

If you want full control: export the code from Lovable (React + Vite) and deploy to Vercel or Netlify for free. Connect the GitHub repo to Vercel for automatic re-deploys.

---

## Performance & Cost Summary

| Concern | Decision | Result |
|---------|----------|--------|
| API calls per run | Incremental: stop at known slug | First run: up to 1,000 jobs; subsequent: typically 50–200 |
| Database writes | Batch upserts of 200 rows | Minimizes PostgREST round trips; stays under 1 MB limit |
| Gold aggregation | Pure SQL inside Supabase (`refresh_gold()`) | Zero Python ↔ DB data transfer for aggregation |
| Bronze storage | `raw_json` stored in bronze only | Silver/gold hold only structured fields — no JSONB bloat |
| Compute | Prefect Managed work pool | No VM to pay for; free tier covers daily runs |
| Database | Supabase free tier (500 MB) | Daily pipeline generates ~1–5 MB/month |
| Dashboard queries | Reads pre-aggregated views, not raw tables | Fast, lightweight; no complex joins at query time |
| Security | RLS + anon key for dashboard | Bronze never exposed; service key only used by pipeline |

---

## Phase Sequencing

| Phase | Deliverable | Depends On |
|-------|-------------|------------|
| 0 | Project init, accounts, env vars | — |
| 1 | All three DB tables + gold function + RLS | Phase 0 |
| 2 | `config/settings.py` | Phase 0 |
| 3 | Extract task + bronze load tasks | Phases 1, 2 |
| 4 | Silver transform + silver load | Phase 3 |
| 5 | Gold trigger (thin Python wrapper) | Phases 1, 4 |
| 6 | Prefect flow composition | Phases 3–5 |
| 7 | Prefect Cloud deployment + first run | Phase 6 |
| 8 | Dashboard views + Lovable prompt | Phase 7 (data must exist) |

Phases 3–5 can be developed and tested locally with `uv run python flows/job_pipeline.py` before pushing to Prefect Cloud.
