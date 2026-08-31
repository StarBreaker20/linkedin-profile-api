"""FastAPI application — the public HTTPS surface.

Endpoints:
  GET /health          liveness of the service itself
  GET /session/status  whether the configured LinkedIn cookie is still valid
  GET /profile?url=... scrape a LinkedIn profile into structured JSON

Interactive docs are auto-generated at /docs (Swagger) and /redoc.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app import __version__
from app.cache import TTLCache
from app.config import get_settings
from app.errors import AuthenticationError, LinkedInError
from app.linkedin.parser import parse_dash_profile
from app.schemas import ProfileResponse, ResponseMeta
from app.service import ProfileService
from app.session import build_pool

_SAMPLE_PROFILE = json.loads((Path(__file__).parent / "data" / "sample_dash_profile.json").read_text())

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.cache = TTLCache(settings.cache_ttl_seconds)
    app.state.pool = build_pool(settings)
    app.state.service = ProfileService(settings, app.state.cache, app.state.pool)
    yield


app = FastAPI(
    title="LinkedIn Profile API",
    version=__version__,
    description=(
        "A browser-free, reverse-engineered API that turns a LinkedIn profile URL into "
        "structured JSON by calling LinkedIn's internal Voyager endpoints directly."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── auth dependencies ────────────────────────────────────────────────────────
async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise AuthenticationError("Missing or invalid API key.", detail={"header": "X-API-Key"})


async def require_admin(x_api_key: str | None = Header(default=None)) -> None:
    # Admin routes are OFF unless an API_KEY is configured, and then require it.
    if not settings.api_key:
        raise AuthenticationError(
            "Admin endpoints are disabled. Set the API_KEY variable to enable them.",
            detail={"hint": "no API_KEY configured"},
        )
    if x_api_key != settings.api_key:
        raise AuthenticationError("Missing or invalid API key.", detail={"header": "X-API-Key"})


class SessionUpdate(BaseModel):
    li_at: str
    jsessionid: str


# ── error handling ───────────────────────────────────────────────────────────
@app.exception_handler(LinkedInError)
async def linkedin_error_handler(_request, exc: LinkedInError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/session/status")
async def session_status() -> dict:
    return await app.state.service.session_status()


@app.post("/admin/session", dependencies=[Depends(require_admin)])
async def refresh_session(body: SessionUpdate) -> dict:
    """Hot-swap a fresh LinkedIn cookie into the running service — no redeploy.

    Protected by `X-API-Key`. Mint the cookie on a residential machine (where LinkedIn
    login works), then POST it here; it becomes the preferred cookie immediately. See
    `scripts/refresh_cookie.py`.
    """
    cookie = await app.state.pool.upsert(body.li_at.strip(), body.jsessionid.strip())
    return {"ok": True, "active": cookie.label, "pool": app.state.pool.status()}


@app.get("/demo", response_model=ProfileResponse)
async def demo() -> ProfileResponse:
    """Parse a bundled SYNTHETIC sample through the real pipeline.

    Lets anyone see the exact output shape live — even from a cloud IP that LinkedIn
    blocks (HTTP 999) for real fetches. The data is fictional, not scraped.
    """
    profile, sections = parse_dash_profile(_SAMPLE_PROFILE, "ada-byron")
    meta = ResponseMeta(
        source_url="sample://synthetic-demo-profile (not scraped)",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        partial=any(not s.ok for s in sections),
        sections=sections,
    )
    return ProfileResponse(meta=meta, profile=profile)


@app.get("/profile", response_model=ProfileResponse, dependencies=[Depends(require_api_key)])
async def get_profile(
    url: str = Query(..., description="A LinkedIn profile URL, e.g. https://www.linkedin.com/in/williamhgates/"),
    include_raw: bool = Query(False, description="Include the raw Voyager payload for verification."),
) -> ProfileResponse:
    return await app.state.service.get_profile(url, include_raw=include_raw)
