"""Container entrypoint: `python -m app`.

Two deploy-portability concerns handled here:
  * Port from $PORT is read **in Python**, not via shell expansion — some platforms
    (e.g. Railway) execute the image CMD without a shell, which would leave a literal
    "${PORT:-8000}" unexpanded and crash uvicorn.
  * Bind to "::" (IPv6 dual-stack) by default. Railway (and some other PaaS) route to the
    container over IPv6; a process listening only on 0.0.0.0 (IPv4) is unreachable and the
    platform returns 502. On Linux, "::" also accepts IPv4 connections.
Both HOST and PORT can still be overridden via env.
"""
from __future__ import annotations

import os
import socket

import uvicorn


def _default_host() -> str:
    """Prefer IPv6 dual-stack ("::") so Railway's IPv6 routing/health-checks can reach us;
    fall back to IPv4 ("0.0.0.0") on hosts without IPv6 (some CI / sandboxes)."""
    try:
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM).close()
        return "::"
    except OSError:
        return "0.0.0.0"


if __name__ == "__main__":
    host = os.environ.get("HOST") or _default_host()
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port)
