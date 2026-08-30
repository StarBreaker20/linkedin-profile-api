"""Tests for the shape-stable, deterministic building blocks.

These run with no network and no cookie — they cover URL parsing/SSRF guard, CSRF
derivation, Rest.li encoding, image/date helpers, and the URN denormalizer.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import InvalidProfileURLError
from app.linkedin.decode import VoyagerGraph
from app.linkedin.endpoints import build_graphql_path, encode_restli
from app.linkedin.parser import date_range, image_from_vector
from app.linkedin.urls import extract_public_id


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.linkedin.com/in/williamhgates/", "williamhgates"),
        ("linkedin.com/in/john-doe-123", "john-doe-123"),
        ("https://in.linkedin.com/in/foo?originalSubdomain=in", "foo"),
        ("https://www.linkedin.com/in/some%2Duser", "some-user"),
    ],
)
def test_extract_public_id_valid(url, expected):
    assert extract_public_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/in/foo",
        "https://www.linkedin.com/company/acme",
        "not-a-url",
        "",
    ],
)
def test_extract_public_id_invalid(url):
    with pytest.raises(InvalidProfileURLError):
        extract_public_id(url)


def test_csrf_token_strips_quotes():
    s = Settings(linkedin_jsessionid='"ajax:1234567890"')
    assert s.csrf_token == "ajax:1234567890"


def test_encode_restli_scalars_and_containers():
    assert encode_restli({"vanityName": "williamhgates"}) == "(vanityName:williamhgates)"
    assert encode_restli(["a", "b"]) == "List(a,b)"
    assert encode_restli({"profileUrn": "urn:li:fsd_profile:ABC"}) == "(profileUrn:urn%3Ali%3Afsd_profile%3AABC)"


def test_build_graphql_path():
    path = build_graphql_path("voyagerIdentityDashProfiles.abc123", {"vanityName": "foo"})
    assert path.startswith("/graphql?")
    assert "queryId=voyagerIdentityDashProfiles.abc123" in path
    assert "variables=(vanityName:foo)" in path


def test_image_from_vector_picks_largest():
    vector = {
        "rootUrl": "https://media.licdn.com/dms/image/",
        "artifacts": [
            {"width": 100, "height": 100, "fileIdentifyingUrlPathSegment": "100_100/pic.jpg"},
            {"width": 400, "height": 400, "fileIdentifyingUrlPathSegment": "400_400/pic.jpg"},
        ],
    }
    img = image_from_vector(vector)
    assert img is not None
    assert img.url.endswith("400_400/pic.jpg")
    assert len(img.artifacts) == 2


def test_image_from_vector_handles_missing():
    assert image_from_vector(None) is None
    assert image_from_vector({"rootUrl": "x"}) is None


def test_date_range():
    dr = date_range({"startDate": {"year": 2020, "month": 3}, "endDate": {"year": 2022}})
    assert dr is not None
    assert dr.start.year == 2020
    assert dr.start.month == 3
    assert dr.end.year == 2022
    assert date_range(None) is None


def test_voyager_graph_denormalizes():
    response = {
        "data": {"*elements": ["urn:li:fsd_profilePosition:1"]},
        "included": [
            {"entityUrn": "urn:li:fsd_profilePosition:1", "$type": "com.linkedin.voyager.dash.identity.profile.Position", "title": "Engineer"},
            {"entityUrn": "urn:li:fsd_company:9", "$type": "com.linkedin.voyager.dash.organization.Company", "name": "Acme"},
        ],
    }
    graph = VoyagerGraph(response)
    assert graph.resolve("urn:li:fsd_company:9")["name"] == "Acme"
    assert len(graph.by_type("Position")) == 1
    positions = graph.deref(graph.data, "elements")
    assert positions[0]["title"] == "Engineer"
