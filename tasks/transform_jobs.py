import re
from datetime import datetime, timezone, date
from prefect import task, get_run_logger


# Maps common tag variants to a canonical tech name.
# Extend this dict as new aliases appear in the data.
TECH_ALIASES: dict[str, str] = {
    "react.js": "React",        "reactjs": "React",
    "node.js": "Node.js",       "nodejs": "Node.js",
    "next.js": "Next.js",       "nextjs": "Next.js",
    "vue.js": "Vue",            "vuejs": "Vue",
    "nuxt.js": "Nuxt",          "nuxtjs": "Nuxt",
    "express.js": "Express",    "expressjs": "Express",
    "postgres": "PostgreSQL",   "postgresql": "PostgreSQL",
    "mongo": "MongoDB",         "mongodb": "MongoDB",
    "ml": "Machine Learning",
    "ai": "AI",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "ts": "TypeScript",
    "js": "JavaScript",
    "py": "Python",
    "tf": "Terraform",
}

# Lower-cased country/region strings to detect in location fields.
# Order matters: more specific entries should come first.
KNOWN_COUNTRIES: list[tuple[str, str]] = [
    ("united states", "United States"),
    ("usa", "United States"),
    ("u.s.a", "United States"),
    ("united kingdom", "United Kingdom"),
    ("u.k.", "United Kingdom"),
    (" uk", "United Kingdom"),       # leading space avoids matching "bulk", "duke", etc.
    ("germany", "Germany"),
    ("deutschland", "Germany"),
    ("canada", "Canada"),
    ("france", "France"),
    ("netherlands", "Netherlands"),
    ("australia", "Australia"),
    ("india", "India"),
    ("spain", "Spain"),
    ("portugal", "Portugal"),
    ("brazil", "Brazil"),
    ("poland", "Poland"),
    ("sweden", "Sweden"),
    ("norway", "Norway"),
    ("denmark", "Denmark"),
    ("finland", "Finland"),
    ("switzerland", "Switzerland"),
    ("austria", "Austria"),
    ("singapore", "Singapore"),
    ("remote", "Remote"),
    ("worldwide", "Remote"),
    ("anywhere", "Remote"),
    ("global", "Remote"),
]


def normalize_tech_tag(tag: str) -> str:
    """Returns the canonical name for a tech tag, or the original (title-cased) if unknown."""
    key = tag.lower().strip()
    return TECH_ALIASES.get(key, tag.strip())


def parse_location(location: str | None) -> tuple[str | None, str | None]:
    """
    Parses a free-text location string into (city, country).
    Returns (None, None) if location is empty.
    """
    if not location:
        return None, None

    lower = " " + location.lower()  # leading space helps the " uk" pattern above

    for pattern, canonical in KNOWN_COUNTRIES:
        if pattern in lower:
            # Everything before the matched country token is treated as the city
            idx = lower.find(pattern)
            before = lower[:idx].strip(" ,/")
            city = before.title() if before else None
            return city or None, canonical

    # No known country matched — treat the whole string as city
    return location.strip().title(), None


def _parse_date(created_at) -> str | None:
    """
    Arbeitnow returns created_at as a Unix timestamp (int).
    Converts to 'YYYY-MM-DD' string, or None if missing/unparseable.
    """
    if created_at is None:
        return None
    try:
        if isinstance(created_at, int):
            return datetime.fromtimestamp(created_at, tz=timezone.utc).date().isoformat()
        # Fallback: string like "YYYY-MM-DD HH:MM:SS"
        return str(created_at)[:10]
    except Exception:
        return None


@task(name="transform-jobs")
def transform_jobs(raw_jobs: list[dict]) -> list[dict]:
    """Cleans and normalises bronze records into silver-ready dicts."""
    logger = get_run_logger()
    now = datetime.now(timezone.utc).isoformat()
    cleaned: list[dict] = []

    for job in raw_jobs:
        tags: list[str] = job.get("tags") or []
        tech_stack = [normalize_tech_tag(t) for t in tags]
        tech_stack = list(dict.fromkeys(tech_stack))  # dedupe, preserve insertion order

        city, country = parse_location(job.get("location"))

        # Arbeitnow's public endpoint does not expose structured salary fields.
        # salary_min/max stay NULL; extend here if a future API version adds them.
        cleaned.append({
            "slug":         job["slug"],
            "title":        job.get("title"),
            "company":      job.get("company_name") or "Unknown",
            "country":      country,
            "city":         city,
            "remote":       job.get("remote", False),
            "tech_stack":   tech_stack,
            "job_types":    job.get("job_types") or [],
            "salary_min":   None,
            "salary_max":   None,
            "currency":     None,
            "posted_date":  _parse_date(job.get("created_at")),
            "source_url":   job.get("url"),
            "processed_at": now,
        })

    logger.info(f"Transformed {len(cleaned)} jobs for silver layer")
    return cleaned
