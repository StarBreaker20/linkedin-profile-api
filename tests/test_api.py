"""HTTP-layer tests via FastAPI's TestClient — proves the app boots and the route →
service → error-taxonomy path works end to end, with no cookie and no network.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_openapi_exposes_profile_route():
    with TestClient(app) as client:
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert "/profile" in r.json()["paths"]


def test_profile_rejects_non_linkedin_url():
    # URL validation / SSRF guard runs before any network or session check.
    with TestClient(app) as client:
        r = client.get("/profile", params={"url": "https://example.com/in/foo"})
        assert r.status_code == 422
        assert r.json()["error"] == "invalid_profile_url"


def test_profile_requires_configured_session():
    # A valid LinkedIn URL with no cookie configured -> a clean 503, not a 500.
    with TestClient(app) as client:
        r = client.get("/profile", params={"url": "https://www.linkedin.com/in/williamhgates/"})
        assert r.status_code == 503
        assert r.json()["error"] == "configuration_error"
