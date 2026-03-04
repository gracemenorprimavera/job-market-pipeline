import json
import resend
from datetime import datetime, timezone

from prefect import task, get_run_logger
from prefect.artifacts import create_markdown_artifact
from supabase import create_client

from config.settings import settings


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_key)


# ---------------------------------------------------------------------------
# Gold summary fetch
# ---------------------------------------------------------------------------

@task(name="get-gold-summary")
def get_gold_summary() -> list[dict]:
    """Fetches the 7 most recent gold rows for use in the artifact and email."""
    client = _get_supabase()
    result = (
        client.table("job_market_summary")
        .select("summary_date,job_count,remote_count,remote_ratio,top_tech_stack")
        .order("summary_date", desc=True)
        .limit(7)
        .execute()
    )
    return result.data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _top_tech_str(top_tech_stack, n: int = 8) -> str:
    """Returns a comma-separated string of the top N tech tags from a gold row."""
    if not top_tech_stack:
        return "—"
    try:
        items = json.loads(top_tech_stack) if isinstance(top_tech_stack, str) else top_tech_stack
        return ", ".join(item["tech"] for item in items[:n] if item.get("tech"))
    except Exception:
        return "—"


def _build_markdown(
    run_time: str,
    dq_bronze: dict,
    bronze_count: int,
    dq_silver: dict,
    silver_count: int,
    gold_rows: list[dict],
) -> str:
    latest_tech = _top_tech_str(gold_rows[0].get("top_tech_stack") if gold_rows else None)

    gold_table_rows = "\n".join(
        f"| {r['summary_date']} | {r['job_count']:,} | "
        f"{r['remote_count']:,} | {r['remote_ratio'] or 0:.1f}% |"
        for r in gold_rows
    )

    dq_bronze_status = "✅ No issues" if dq_bronze["null_companies"] == 0 and dq_bronze["duplicate_slugs"] == 0 else "⚠️ Warnings"
    dq_silver_status = "✅ No issues" if dq_silver["null_companies"] == 0 and dq_silver["null_dates"] == 0 else "⚠️ Warnings"

    return f"""## Job Market Pipeline — Run Summary

**Run time:** {run_time}

---

### Extraction & Load

| Layer | Rows fetched | Rows loaded |
|-------|-------------|-------------|
| Bronze (`jobs_raw`) | {dq_bronze['total']:,} | {bronze_count:,} |
| Silver (`jobs_clean`) | {dq_silver['total']:,} | {silver_count:,} |

---

### Data Quality

| Layer | Status | Detail |
|-------|--------|--------|
| Bronze | {dq_bronze_status} | {dq_bronze['null_companies']} null companies · {dq_bronze['duplicate_slugs']} duplicate slugs (auto-deduped) |
| Silver | {dq_silver_status} | {dq_silver['null_companies']} unknown companies · {dq_silver['null_dates']} null dates |

---

### Gold Layer — Last 7 Days

| Date | Jobs | Remote | Remote % |
|------|------|--------|----------|
{gold_table_rows}

---

### Top Technologies (Most Recent Day)

{latest_tech}
"""


def _build_html(
    run_time: str,
    dq_bronze: dict,
    bronze_count: int,
    dq_silver: dict,
    silver_count: int,
    gold_rows: list[dict],
) -> str:
    latest_tech = _top_tech_str(gold_rows[0].get("top_tech_stack") if gold_rows else None)

    gold_rows_html = "\n".join(
        f"<tr><td>{r['summary_date']}</td><td>{r['job_count']:,}</td>"
        f"<td>{r['remote_count']:,}</td><td>{r['remote_ratio'] or 0:.1f}%</td></tr>"
        for r in gold_rows
    )

    dq_bronze_badge = "✅" if dq_bronze["null_companies"] == 0 and dq_bronze["duplicate_slugs"] == 0 else "⚠️"
    dq_silver_badge = "✅" if dq_silver["null_companies"] == 0 and dq_silver["null_dates"] == 0 else "⚠️"

    return f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 680px; margin: 0 auto; color: #1e293b; }}
  h2   {{ color: #6366f1; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
  h3   {{ color: #334155; margin-top: 28px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th   {{ background: #f1f5f9; text-align: left; padding: 8px 12px; font-size: 13px; }}
  td   {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
  .tag {{ display: inline-block; background: #ede9fe; color: #5b21b6; border-radius: 4px;
          padding: 2px 8px; margin: 2px; font-size: 13px; }}
  .muted {{ color: #94a3b8; font-size: 12px; }}
</style>
</head>
<body>
<h2>Job Market Pipeline — Run Summary</h2>
<p class="muted">Run time: {run_time}</p>

<h3>Extraction &amp; Load</h3>
<table>
  <tr><th>Layer</th><th>Rows fetched</th><th>Rows loaded</th></tr>
  <tr><td>Bronze (jobs_raw)</td><td>{dq_bronze['total']:,}</td><td>{bronze_count:,}</td></tr>
  <tr><td>Silver (jobs_clean)</td><td>{dq_silver['total']:,}</td><td>{silver_count:,}</td></tr>
</table>

<h3>Data Quality</h3>
<table>
  <tr><th>Layer</th><th>Status</th><th>Detail</th></tr>
  <tr>
    <td>Bronze</td>
    <td>{dq_bronze_badge}</td>
    <td>{dq_bronze['null_companies']} null companies · {dq_bronze['duplicate_slugs']} duplicate slugs (auto-deduped)</td>
  </tr>
  <tr>
    <td>Silver</td>
    <td>{dq_silver_badge}</td>
    <td>{dq_silver['null_companies']} unknown companies · {dq_silver['null_dates']} null dates</td>
  </tr>
</table>

<h3>Gold Layer — Last 7 Days</h3>
<table>
  <tr><th>Date</th><th>Jobs</th><th>Remote</th><th>Remote %</th></tr>
  {gold_rows_html}
</table>

<h3>Top Technologies (Most Recent Day)</h3>
<p>{"".join(f'<span class="tag">{t.strip()}</span>' for t in latest_tech.split(",") if t.strip())}</p>

<hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px">
<p class="muted">Sent by the job-market-pipeline · Prefect Cloud</p>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(name="create-pipeline-artifact")
def create_pipeline_artifact(
    dq_bronze: dict,
    bronze_count: int,
    dq_silver: dict,
    silver_count: int,
    gold_rows: list[dict],
) -> None:
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    markdown = _build_markdown(run_time, dq_bronze, bronze_count, dq_silver, silver_count, gold_rows)
    create_markdown_artifact(
        key="pipeline-summary",
        markdown=markdown,
        description="Pipeline run summary — extraction, DQ checks, and gold layer stats",
    )
    get_run_logger().info("Pipeline artifact created")


@task(name="send-summary-email")
def send_summary_email(
    dq_bronze: dict,
    bronze_count: int,
    dq_silver: dict,
    silver_count: int,
    gold_rows: list[dict],
) -> None:
    logger = get_run_logger()

    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY not set — skipping email notification")
        return

    if not settings.email_recipient:
        logger.warning("EMAIL_RECIPIENT not set — skipping email notification")
        return

    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _build_html(run_time, dq_bronze, bronze_count, dq_silver, silver_count, gold_rows)

    resend.api_key = settings.resend_api_key
    resend.Emails.send({
        "from":    settings.email_from,
        "to":      [settings.email_recipient],
        "subject": f"✅ Job Market Pipeline — {run_time}",
        "html":    html,
    })

    logger.info(f"Summary email sent to {settings.email_recipient}")
