"""Parser wiring tests against a synthetic profileView payload.

This proves the assembler maps fields onto the schema and returns per-section statuses.
Once we capture a real Voyager payload it gets saved (sanitized) under tests/fixtures/
and asserted here too — same test shape, real data.
"""
from __future__ import annotations

from app.linkedin.parser import parse_contact_info, parse_profile_view

PROFILE_VIEW = {
    "profile": {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "headline": "Mathematician & first programmer",
        "summary": "Notes on the Analytical Engine.",
        "geoLocationName": "London, England",
        "industryName": "Software Development",
        "entityUrn": "urn:li:fs_profile:ada",
    },
    "positionView": {
        "elements": [
            {
                "title": "Analyst",
                "companyName": "Analytical Engines",
                "locationName": "London",
                "description": "Wrote the first algorithm.",
                "timePeriod": {"startDate": {"year": 1840, "month": 1}},
            }
        ]
    },
    "educationView": {
        "elements": [
            {"schoolName": "Home tutoring", "degreeName": "Mathematics", "fieldOfStudy": "Math",
             "timePeriod": {"startDate": {"year": 1832}}}
        ]
    },
    "skillView": {"elements": [{"name": "Algorithms"}, {"name": "Mathematics"}]},
    "languageView": {"elements": [{"name": "English", "proficiency": "NATIVE_OR_BILINGUAL"}]},
    "certificationView": {"elements": [{"name": "Fellow", "authority": "Royal Society"}]},
}

CONTACT_INFO = {
    "emailAddress": "ada@example.com",
    "websites": [{"url": "https://example.com"}],
    "phoneNumbers": [{"number": "+44 20 0000 0000"}],
    "twitterHandles": [{"name": "ada"}],
}


def test_parse_profile_view_basics_and_sections():
    profile, sections = parse_profile_view(PROFILE_VIEW, "adalovelace")

    assert profile.full_name == "Ada Lovelace"
    assert profile.headline.startswith("Mathematician")
    assert profile.about == "Notes on the Analytical Engine."
    assert profile.location.text == "London, England"
    assert profile.industry == "Software Development"

    assert len(profile.experience) == 1
    assert profile.experience[0].title == "Analyst"
    assert profile.experience[0].company == "Analytical Engines"
    assert profile.experience[0].date_range.start.year == 1840

    assert len(profile.education) == 1
    assert profile.education[0].school == "Home tutoring"

    assert [s.name for s in profile.skills] == ["Algorithms", "Mathematics"]
    assert profile.languages[0].proficiency == "NATIVE_OR_BILINGUAL"
    assert profile.certifications[0].authority == "Royal Society"

    # Every section parsed cleanly.
    assert all(s.ok for s in sections)
    assert {s.section for s in sections} >= {"basics", "experience", "education", "skills"}


def test_parse_contact_info():
    ci = parse_contact_info(CONTACT_INFO)
    assert ci.emails == ["ada@example.com"]
    assert ci.websites == ["https://example.com"]
    assert ci.phones == ["+44 20 0000 0000"]
    assert ci.twitter == ["ada"]


def test_parse_profile_view_tolerates_missing_sections():
    profile, sections = parse_profile_view({"profile": {"firstName": "Solo"}}, "solo")
    assert profile.first_name == "Solo"
    assert profile.experience == []
    # Missing sections still report ok (empty), not crash.
    assert all(s.ok for s in sections)
