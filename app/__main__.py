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

import uvicorn

if __name__ == "__main__":
    # Railway (and most PaaS) route public traffic to the container on 0.0.0.0; bind there
    # by default. HOST can override (e.g. "::" for a pure-IPv6 private-networking setup).
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port)
