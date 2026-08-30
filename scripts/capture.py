"""Automated capture helper.

Fetches a profile via the configured session and dumps the raw Voyager payloads to
captures/ (git-ignored). Use this on a residential IP; from a datacenter it will likely
hit HTTP 999 — in that case use the manual DevTools recipe in docs/CAPTURE_RECIPE.md.

    python -m scripts.capture "https://www.linkedin.com/in/williamhgates/"
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

from app.config import get_settings
from app.linkedin.client import VoyagerClient
from app.linkedin.endpoints import rest_contact_info, rest_profile_view
from app.linkedin.urls import extract_public_id


async def capture(url: str) -> int:
    settings = get_settings()
    if not settings.has_session:
        print("No LinkedIn session configured. Fill .env first (see docs/CAPTURE_RECIPE.md).")
        return 1

    public_id = extract_public_id(url)
    out_dir = pathlib.Path("captures")
    out_dir.mkdir(exist_ok=True)

    async with VoyagerClient(settings) as client:
        payloads: dict[str, object] = {}
        try:
            payloads["profileView"] = await client.get_json(rest_profile_view(public_id))
        except Exception as exc:  # noqa: BLE001 - capture tool: record whatever happened
            payloads["profileView"] = {"_error": repr(exc)}
        try:
            payloads["contactInfo"] = await client.get_json(rest_contact_info(public_id))
        except Exception as exc:  # noqa: BLE001
            payloads["contactInfo"] = {"_error": repr(exc)}

    for name, body in payloads.items():
        path = out_dir / f"{public_id}.{name}.raw.json"
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False))
        print(f"wrote {path}")

    print("\nDone. Paste these back to finalise the parser + build fixtures.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.capture <linkedin-profile-url>")
        return 2
    return asyncio.run(capture(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
