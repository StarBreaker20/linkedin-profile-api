"""Tests for the Dash normalized profile parser — the current primary path.

Runs against a committed fixture that mirrors the real `identity/dash/profiles`
`{data, included}` shape (entity types, `multiLocale`/`*ref` conventions, two-level
PositionGroup→Position experience, inline vectorImage), but with synthetic (non-real)
data so no scraped PII lives in the repo.
"""
from __future__ import annotations

import json
import pathlib

from app.linkedin.parser import parse_dash_profile

# Single source of truth: the packaged sample the /demo endpoint also serves.
FIXTURE = json.loads(
    (pathlib.Path(__file__).parent.parent / "app" / "data" / "sample_dash_profile.json").read_text()
)


def test_parse_dash_profile_basics():
    profile, sections = parse_dash_profile(FIXTURE, "ada-byron")

    assert profile.public_id == "ada-byron"
    assert profile.profile_urn == "urn:li:fsd_profile:SYN1"
    assert profile.full_name == "Ada Byron"
    assert profile.headline.startswith("Mathematician")
    assert profile.about == "Notes on the Analytical Engine."
    assert profile.industry == "Software Development"
    assert profile.location.text == "London, England, United Kingdom"
    assert profile.location.country == "gb"
    # Inline vectorImage -> largest artifact URL assembled from rootUrl + segment.
    assert profile.profile_picture.url == "https://media.licdn.com/pic/400/a.jpg"
    assert all(s.ok for s in sections)


def test_parse_dash_profile_experience_is_two_level():
    profile, _ = parse_dash_profile(FIXTURE, "ada-byron")
    assert len(profile.experience) == 1
    exp = profile.experience[0]
    assert exp.title == "Lead Analyst"
    assert exp.company == "Analytical Engines"
    assert exp.employment_type == "Full-time"
    assert exp.location == "London"
    assert exp.description == "Wrote the first algorithm."
    assert exp.company_logo.url == "https://media.licdn.com/co/200/c.jpg"
    assert exp.company_url == "https://www.linkedin.com/company/analytical-engines/"
    assert exp.date_range.start.year == 1840
    assert exp.date_range.end.year == 1843
    assert exp.date_range.end.month == 6


def test_parse_dash_profile_education_and_empty_skills():
    profile, _ = parse_dash_profile(FIXTURE, "ada-byron")
    assert len(profile.education) == 1
    edu = profile.education[0]
    assert edu.school == "Byron Academy"
    assert edu.degree == "BSc"
    assert edu.field_of_study == "Mathematics"
    assert edu.grade == "First"
    assert edu.school_logo.url == "https://media.licdn.com/sc/200/s.jpg"
    assert edu.date_range.start.year == 1832
    # Skills are a separate card; empty collection here degrades to [], not an error.
    assert profile.skills == []


def test_parse_dash_profile_missing_profile_entity():
    profile, sections = parse_dash_profile({"data": {}, "included": []}, "nobody")
    assert profile.full_name is None
    assert sections[0].ok is False
