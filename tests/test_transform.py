"""
Unit tests for tasks/transform_jobs.py utility functions.
These test pure helper logic without requiring a Prefect runtime or live API.
"""

from tasks.transform_jobs import _parse_date, normalize_tech_tag, parse_location


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------
class TestParseDate:
    def test_unix_timestamp_returns_iso_date(self):
        # 1704067200 == 2024-01-01 00:00:00 UTC
        assert _parse_date(1704067200) == "2024-01-01"

    def test_unix_timestamp_another_date(self):
        # 1735689600 == 2025-01-01 00:00:00 UTC
        assert _parse_date(1735689600) == "2025-01-01"

    def test_string_date_iso(self):
        assert _parse_date("2024-06-15") == "2024-06-15"

    def test_string_datetime_truncated(self):
        assert _parse_date("2024-06-15T10:30:00") == "2024-06-15"

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_invalid_value_falls_back_to_string_slice(self):
        # Non-date strings fall back to str[:10]; "not-a-date" is exactly 10 chars
        assert _parse_date("not-a-date") == "not-a-date"


# ---------------------------------------------------------------------------
# normalize_tech_tag
# ---------------------------------------------------------------------------
class TestNormalizeTechTag:
    def test_known_alias_react(self):
        assert normalize_tech_tag("react.js") == "React"
        assert normalize_tech_tag("reactjs") == "React"

    def test_known_alias_nodejs(self):
        assert normalize_tech_tag("node.js") == "Node.js"
        assert normalize_tech_tag("nodejs") == "Node.js"

    def test_known_alias_postgres(self):
        assert normalize_tech_tag("postgres") == "PostgreSQL"
        assert normalize_tech_tag("postgresql") == "PostgreSQL"

    def test_known_alias_k8s(self):
        assert normalize_tech_tag("k8s") == "Kubernetes"

    def test_unknown_tag_returned_as_is(self):
        assert normalize_tech_tag("Django") == "Django"

    def test_case_insensitive_lookup(self):
        assert normalize_tech_tag("AWS") == "AWS"  # "aws" alias -> "AWS"
        assert normalize_tech_tag("azure") == "Azure"

    def test_strips_whitespace(self):
        assert normalize_tech_tag("  react.js  ") == "React"


# ---------------------------------------------------------------------------
# parse_location
# ---------------------------------------------------------------------------
class TestParseLocation:
    def test_known_country_no_city(self):
        city, country = parse_location("Germany")
        assert country == "Germany"

    def test_known_country_with_city(self):
        city, country = parse_location("Berlin, Germany")
        assert country == "Germany"
        assert city == "Berlin"

    def test_remote_worldwide(self):
        _, country = parse_location("Worldwide")
        assert country == "Remote"

    def test_remote_anywhere(self):
        _, country = parse_location("Anywhere")
        assert country == "Remote"

    def test_unknown_location_becomes_city(self):
        city, country = parse_location("Some Unknown City")
        assert country is None
        assert city == "Some Unknown City"

    def test_none_returns_none_none(self):
        city, country = parse_location(None)
        assert city is None
        assert country is None

    def test_empty_string_returns_none_none(self):
        city, country = parse_location("")
        assert city is None
        assert country is None

    def test_united_states(self):
        _, country = parse_location("New York, United States")
        assert country == "United States"

    def test_united_kingdom(self):
        _, country = parse_location("London, United Kingdom")
        assert country == "United Kingdom"
