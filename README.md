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
│       ├── pr-checks.yml       # CI: lint, types, security, dead code, tests on every PR
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
├── scripts/
│   └── check.py                 # Unified local check runner (all 8 PR checks in one command)
├── tests/
│   ├── __init__.py
│   └── test_transform.py        # Unit tests for transform utility functions
├── .env.example                 # Required environment variables template
├── .secrets.baseline            # detect-secrets baseline (no secrets in repo)
├── prefect.yaml                 # Prefect Cloud deployment config
├── pyproject.toml               # uv project + dependencies + tool configs (ruff/mypy/bandit)
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

### PR Checks (`pr-checks.yml`)

Every pull request targeting `main` must pass **5 parallel quality gates** before it can be merged. All checks are configured in `pyproject.toml` under `[tool.*]` sections.

#### Running checks locally

Use the unified check script — it streams live output and prints a pass/fail summary:

```bash
uv run python scripts/check.py           # run all 8 checks
uv run python scripts/check.py --fix     # auto-fix ruff issues first, then run all
uv run python scripts/check.py --only lint type test   # run specific checks
```

Or run individual checks manually:

```bash
uv run ruff check .                      # lint only
uv run ruff check --fix . && uv run ruff format .   # auto-fix everything
uv run mypy config/ tasks/ flows/ deployment/
uv run bandit -r config/ tasks/ flows/ deployment/ -c pyproject.toml
uv run pip-audit
uv run detect-secrets scan --baseline .secrets.baseline
uv run vulture config/ tasks/ flows/ deployment/ --min-confidence 80
uv run pytest --cov --cov-report=term-missing
```

#### Check reference

| # | Check | Tool | Keyword | Docs |
|---|-------|------|---------|------|
| 1 | Lint | `ruff check` | `lint` | [docs.astral.sh/ruff](https://docs.astral.sh/ruff/rules/) |
| 2 | Format | `ruff format` | `format` | [docs.astral.sh/ruff/formatter](https://docs.astral.sh/ruff/formatter/) |
| 3 | Type Check | `mypy` | `type` | [mypy.readthedocs.io](https://mypy.readthedocs.io/en/stable/) |
| 4 | Security scan | `bandit` | `bandit` | [bandit.readthedocs.io](https://bandit.readthedocs.io/en/latest/) |
| 5 | CVE audit | `pip-audit` | `audit` | [github.com/pypa/pip-audit](https://github.com/pypa/pip-audit) |
| 6 | Secrets | `detect-secrets` | `secrets` | [github.com/Yelp/detect-secrets](https://github.com/Yelp/detect-secrets) |
| 7 | Dead code | `vulture` | `dead` | [github.com/jendrikseipp/vulture](https://github.com/jendrikseipp/vulture) |
| 8 | Tests + Coverage | `pytest-cov` | `test` | [pytest-cov.readthedocs.io](https://pytest-cov.readthedocs.io/en/latest/) |

#### What each check catches

**1. Lint (`ruff check`)** — Fast Python linter that replaces flake8, isort, and pyupgrade. Catches undefined names, unused imports, unsorted imports, shadowed built-ins, and modernisation opportunities (e.g. `timezone.utc` → `datetime.UTC`). Rules are configured in `[tool.ruff.lint]` in `pyproject.toml`.

**2. Format (`ruff format`)** — Enforces consistent code style (quote style, indent, line length). CI runs `--check` mode which fails if any file would be reformatted. Run `ruff format .` locally to auto-fix.

**3. Type Check (`mypy`)** — Static analysis that catches type mismatches, missing return types, and incorrect argument types before runtime. Configured in `[tool.mypy]`. Third-party stubs are allowed to be missing (`ignore_missing_imports = true`) since not all packages ship type info.

**4. Security — Bandit** — Scans for common security pitfalls in Python code: SQL injection risks, use of `assert` in security contexts, unsafe `subprocess` calls, use of weak cryptography (`MD5`, `SHA1`), hardcoded password patterns. Config in `[tool.bandit]`.

**5. Security — pip-audit** — Queries the [OSV](https://osv.dev/) and [PyPI Advisory](https://pypi.org/security/) databases for known CVEs in every installed package. Fails the build if any vulnerability is found, prompting a dependency upgrade.

**6. Secrets Scan (`detect-secrets`)** — Scans every committed file for high-entropy strings and known secret patterns (API keys, JWTs, AWS credentials, etc.). Uses `.secrets.baseline` to track known-safe values. If a new secret is accidentally staged, CI blocks the merge. Update the baseline when a safe value is flagged:

```bash
uv run detect-secrets scan --exclude-files 'uv\.lock|\.venv' > .secrets.baseline
```

**7. Dead Code (`vulture`)** — Finds functions, classes, variables, and imports that are defined but never called or referenced. Helps keep the codebase clean as features evolve. Only flags findings with ≥ 80% confidence to reduce false positives on Prefect-decorated functions. Config in `[tool.vulture]`.

**8. Tests & Coverage (`pytest` + `pytest-cov`)** — Runs the full test suite and measures line coverage. CI fails if coverage drops below the `fail_under` threshold in `[tool.coverage.report]` (currently 30% — raise this as the suite grows). Coverage report shows exactly which lines are untested.

### Deploy (`deploy.yml`)

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
