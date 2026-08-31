"""Automated capture helper.

Fetches a profile via the configured session (Dash endpoint) and dumps the raw Voyager
payload to captures/ (git-ignored). Use this on a residential IP; from a datacenter it may
hit HTTP 999 — in that case use the manual DevTools recipe in docs/CAPTURE_RECIPE.md.

    python -m scripts.capture "https://www.linkedin.com/in/williamhgates/"
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

from app.config import get_settings
from app.linkedin.client import ACCEPT_NORMALIZED, VoyagerClient
from app.linkedin.endpoints import dash_full_profile
from app.linkedin.urls import extract_public_id
from app.session import build_pool


async def capture(url: str) -> int:
    settings = get_settings()
    cookie = build_pool(settings).current()
    if cookie is None:
        print("No LinkedIn session configured. Fill .env first (see docs/CAPTURE_RECIPE.md).")
        return 1

    public_id = extract_public_id(url)
    out_dir = pathlib.Path("captures")
    out_dir.mkdir(exist_ok=True)

    async with VoyagerClient(settings, cookie) as client:
        try:
            body: object = await client.get_json(dash_full_profile(public_id), accept=ACCEPT_NORMALIZED)
        except Exception as exc:  # noqa: BLE001 - capture tool: record whatever happened
            body = {"_error": repr(exc)}

    path = out_dir / f"{public_id}.dashProfile.raw.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    print(f"wrote {path}\n\nPaste this back to finalise the parser / build fixtures.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.capture <linkedin-profile-url>")
        return 2
    return asyncio.run(capture(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
