# Job Market Pipeline

A daily ELT data pipeline that fetches job listings from the [Arbeitnow](https://www.arbeitnow.com/) public API, stores and transforms them in Supabase using a medallion architecture (bronze → silver → gold), and visualises analytics in a Lovable dashboard.

## Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | Prefect Cloud (Managed Work Pool — `default-work-pool`) |
| Data source | Arbeitnow public API (free, no auth) |
| Database | Supabase PostgreSQL |
| Language | Python 3.13 + uv |
| Email notifications | Resend |
| Dashboard | Lovable (planned) |
| CI/CD | GitHub Actions |

## Architecture

```
Arbeitnow API
  → Bronze  (jobs_raw)            raw API responses, deduped by slug
  → Silver  (jobs_clean)          cleaned, normalised, tech stack extracted
  → Gold    (job_market_summary)  daily aggregates via PostgreSQL function
  → Prefect Artifact              markdown run summary in Prefect Cloud UI
  → Email notification            Resend HTML email after each run
  → Lovable dashboard             (planned)
```

## Project Structure

```
job-market-pipeline/
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI: auto-deploy + email on merge to main
├── config/
│   └── settings.py             # Pydantic settings (reads .env)
├── deployment/
│   ├── deploy.py               # Sets Prefect variables, runs prefect deploy --all
│   └── notify_deploy.py        # Sends Resend email after CI deploy
├── flows/
│   └── job_pipeline.py         # Main Prefect flow (entry point)
├── sql/
│   ├── bronze_schema.sql        # jobs_raw table + indexes
│   ├── silver_schema.sql        # jobs_clean table + indexes
│   ├── gold_schema.sql          # job_market_summary table
│   ├── gold_refresh_fn.sql      # refresh_gold() PostgreSQL function
│   └── rls_policies.sql         # Row Level Security policies
├── tasks/
│   ├── extract_jobs.py          # Paginate Arbeitnow API (incremental by slug)
│   ├── transform_jobs.py        # Clean + normalise raw jobs
│   ├── load_supabase.py         # Upsert to bronze/silver, call refresh_gold()
│   └── notify.py                # Prefect artifact + Resend email summary
├── .env.example                 # Required environment variables template
├── prefect.yaml                 # Prefect Cloud deployment config
├── pyproject.toml               # uv project + dependencies
└── run_local.py                 # Local dev launcher (loads .env before Prefect init)
```

## Local Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Fill in all values:

```
SUPABASE_URL=             # Project Settings > API > Project URL
SUPABASE_SERVICE_KEY=     # Project Settings > API > service_role (JWT)
PREFECT_API_KEY=          # app.prefect.io > Settings > API Keys
PREFECT_API_URL=          # app.prefect.io > Settings > Workspaces
RESEND_API_KEY=           # resend.com dashboard (leave blank to disable email)
EMAIL_FROM=               # verified sender domain in Resend
EMAIL_RECIPIENT=          # destination address for pipeline summaries
```

### 3. Run the SQL schema in Supabase

Run these files in order in the Supabase SQL Editor:

1. `sql/bronze_schema.sql`
2. `sql/silver_schema.sql`
3. `sql/gold_schema.sql`
4. `sql/gold_refresh_fn.sql`
5. `sql/rls_policies.sql`

### 4. Run locally

```bash
uv run python run_local.py
```

`run_local.py` loads `.env` before Prefect initialises so `PREFECT_API_KEY` is
available in the environment at startup.

For a full refresh (ignores existing slugs):

```bash
uv run python run_local.py --full-refresh
```

### 5. Run tests

```bash
uv run pytest
```

## Prefect Cloud Deployment

### One-time deploy

```bash
uv run python deployment/deploy.py
```

This script:
1. Reads your `.env` and pushes the 5 pipeline secrets as Prefect Cloud Variables
2. Runs `prefect deploy --all` using `prefect.yaml`

The deployment runs daily at **06:00 UTC** via the `default-work-pool` managed work pool.

## CI/CD — GitHub Actions

`.github/workflows/deploy.yml` triggers on every push to `main` (i.e. merged PR):

1. Installs Python 3.13 + uv + dependencies
2. Runs `deployment/deploy.py` to update Prefect variables and redeploy the flow
3. Always runs `deployment/notify_deploy.py` — sends a Resend email with deploy status (success or failure), commit SHA, actor, and a link to the Actions run log

### Required GitHub Secrets

Add these in **Settings > Secrets and variables > Actions** of your repo:

| Secret | Description |
|--------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | service_role JWT |
| `PREFECT_API_KEY` | Prefect Cloud API key |
| `PREFECT_API_URL` | Prefect Cloud workspace URL |
| `RESEND_API_KEY` | Resend API key |
| `EMAIL_FROM` | Verified sender address |
| `EMAIL_RECIPIENT` | Notification destination |

## Git Workflow

- All new features go on a `feature/<name>` branch — never push directly to `main`
- Open a PR; merging to `main` triggers the CI deploy workflow automatically

## Pipeline Behaviour

| Scenario | Behaviour |
|----------|-----------|
| First run | `full_refresh=true` fetches all available pages |
| Daily run | Incremental — stops when a known slug is encountered |
| Duplicate slugs | Deduped in memory before each batch upsert |
| No new jobs | Pipeline exits early after bronze load |
| Email disabled | Skip silently if `RESEND_API_KEY` is blank |
| Gold refresh | PostgreSQL function `refresh_gold()` called via Supabase RPC — no data transfer to Python |

## Data Quality Checks

| Layer | Checks |
|-------|--------|
| Bronze | Null companies, duplicate slugs (auto-deduped) |
| Silver | Null companies, null posted dates |

Results appear in the Prefect Cloud artifact (`pipeline-summary` key) and the email summary after each run.
