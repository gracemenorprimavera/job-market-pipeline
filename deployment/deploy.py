"""
Registers Prefect Cloud variables and deploys the flow.
Run once: uv run python deployment/deploy.py
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env for local runs; override=False keeps CI secrets (already in env) intact
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

VARIABLES = {
    "supabase_url": os.environ["SUPABASE_URL"],
    "supabase_service_key": os.environ["SUPABASE_SERVICE_KEY"],
    "resend_api_key": os.environ.get("RESEND_API_KEY", ""),
    "email_from": os.environ.get("EMAIL_FROM", "onboarding@resend.dev"),
    "email_recipient": os.environ.get("EMAIL_RECIPIENT", ""),
}

ROOT = Path(__file__).parent.parent


def run(cmd: list[str], **kwargs) -> None:
    result = subprocess.run(cmd, cwd=ROOT, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    print("-- Setting Prefect variables ------------------------------")
    for name, value in VARIABLES.items():
        if not value:
            print(f"  SKIP  {name} (empty — set in .env to enable)")
            continue
        run(["prefect", "variable", "set", name, value], capture_output=False)
        print(f"  SET   {name}")

    print("\n-- Deploying flow to Prefect Cloud ------------------------")
    run(["prefect", "deploy", "--all"], capture_output=False)
    print("\nDone. Check app.prefect.io > Deployments.")


if __name__ == "__main__":
    main()
