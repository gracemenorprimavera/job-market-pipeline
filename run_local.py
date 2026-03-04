"""
Local development runner.
Loads .env, sets all vars in the process environment, then runs a full refresh.
Usage: uv run python run_local.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env into os.environ before Prefect initialises
load_dotenv(Path(__file__).parent / ".env", override=True)

# Now import and run the flow (env vars are already set)
from flows.job_pipeline import job_pipeline  # noqa: E402

if __name__ == "__main__":
    job_pipeline(full_refresh=True)
