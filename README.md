# Job Market Pipeline

A daily ELT data pipeline that fetches job listings from the Arbeitnow public API, stores and transforms them in Supabase using a medallion architecture (bronze → silver → gold), and visualises analytics in a Lovable dashboard.

## Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | Prefect Cloud (Managed Work Pool) |
| Data source | Arbeitnow public API (free, no auth) |
| Database | Supabase PostgreSQL |
| Language | Python 3.13 + uv |
| Dashboard | Lovable |

## Architecture

```
Arbeitnow API
  → Bronze (jobs_raw)       — raw API responses
  → Silver (jobs_clean)     — cleaned, normalised
  → Gold (job_market_summary) — daily aggregates
  → Lovable dashboard
```

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment variables

```bash
cp .env.example .env
# fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, PREFECT_API_KEY, PREFECT_API_URL
```

### 3. Run the pipeline locally (full refresh)

```bash
uv run python flows/job_pipeline.py
```

### 4. Deploy to Prefect Cloud

```bash
prefect cloud login --key $PREFECT_API_KEY
prefect deploy --all
```

## Project Structure

```
flows/           # Prefect flow entry point
tasks/           # Extract, transform, load tasks
sql/             # Schema DDL and gold refresh function
config/          # Pydantic settings
deployment/      # Prefect Cloud deployment script
```

## Development

```bash
uv run pytest    # run tests
```
