"""Push a fresh LinkedIn cookie to the running service — no redeploy.

When the deployed cookie dies, grab a fresh `li_at` + `JSESSIONID` from a logged-in
browser (DevTools → Application → Cookies), then run this on your own machine. It POSTs
the cookie to the service's protected `/admin/session` endpoint, which hot-swaps it in.

    BASE_URL="https://<your-app>.up.railway.app" \
    API_KEY="<your api key>" \
    LI_AT="AQEDAT..." \
    JSESSIONID='"ajax:1234567890"' \
    python -m scripts.refresh_cookie

Login itself stays manual/in-browser on purpose: LinkedIn login triggers CAPTCHA/OTP/
device challenges and cannot be reliably automated from a server. This tool only delivers
a cookie you've already obtained.
"""
from __future__ import annotations

import os

import httpx


def main() -> int:
    base = (os.environ.get("BASE_URL") or "").rstrip("/")
    api_key = os.environ.get("API_KEY", "")
    li_at = os.environ.get("LI_AT", "")
    jsessionid = os.environ.get("JSESSIONID", "")

    if not (base and li_at and jsessionid):
        print("Set BASE_URL, LI_AT and JSESSIONID (and API_KEY). See the module docstring.")
        return 2

    try:
        resp = httpx.post(
            f"{base}/admin/session",
            headers={"X-API-Key": api_key},
            json={"li_at": li_at, "jsessionid": jsessionid},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        print(f"Request failed: {exc}")
        return 1

    print(resp.status_code, resp.text)
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
