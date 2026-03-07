"""
Sends a Resend email when the GitHub Actions deployment completes.
Called automatically from .github/workflows/deploy.yml with DEPLOY_STATUS set.
"""

import os

import resend


def main() -> None:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print("RESEND_API_KEY not set -- skipping deploy notification")
        return

    recipient = os.environ.get("EMAIL_RECIPIENT", "")
    if not recipient:
        print("EMAIL_RECIPIENT not set -- skipping deploy notification")
        return

    email_from = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")
    status = os.environ.get("DEPLOY_STATUS", "unknown").lower()
    actor = os.environ.get("GH_ACTOR", "unknown")
    sha = os.environ.get("GH_SHA", "")[:7]
    run_url = os.environ.get("GH_RUN_URL", "#")
    commit_msg = os.environ.get("GH_COMMIT_MSG", "").split("\n")[0]  # first line only

    is_success = status == "success"
    emoji = "OK" if is_success else "FAIL"
    status_label = "Succeeded" if is_success else "Failed"
    accent = "#16a34a" if is_success else "#dc2626"
    badge_bg = "#dcfce7" if is_success else "#fee2e2"
    badge_fg = "#15803d" if is_success else "#b91c1c"

    commit_row = f"<tr><td>Commit message</td><td>{commit_msg}</td></tr>" if commit_msg else ""

    html = f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; color: #1e293b; }}
  h2   {{ color: {accent}; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
  .pill {{ display: inline-block; background: {badge_bg}; color: {badge_fg};
           border-radius: 9999px; padding: 2px 10px; font-size: 13px; font-weight: 600; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  td    {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
  td:first-child {{ color: #64748b; width: 140px; }}
  a     {{ color: #6366f1; }}
  code  {{ background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 13px; }}
  .muted {{ color: #94a3b8; font-size: 12px; }}
</style>
</head>
<body>
<h2>[{emoji}] Prefect Deployment {status_label}</h2>
<table>
  <tr><td>Status</td><td><span class="pill">{status_label}</span></td></tr>
  <tr><td>Commit</td><td><code>{sha}</code></td></tr>
  <tr><td>Pushed by</td><td>{actor}</td></tr>
  {commit_row}
  <tr><td>Run log</td><td><a href="{run_url}">View on GitHub Actions</a></td></tr>
</table>
<hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px">
<p class="muted">Sent by job-market-pipeline CI</p>
</body>
</html>"""

    resend.api_key = api_key
    resend.Emails.send(
        {
            "from": email_from,
            "to": [recipient],
            "subject": f"[{emoji}] Prefect Deploy {status_label} -- {sha}",
            "html": html,
        }
    )
    print(f"Deploy notification sent to {recipient} (status: {status_label})")


if __name__ == "__main__":
    main()
