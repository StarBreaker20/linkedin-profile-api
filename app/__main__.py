"""Container entrypoint: `python -m app`.

Resolves the listen port from $PORT **in Python** rather than via shell expansion.
Some platforms (e.g. Railway) execute the image's CMD without a shell, which would leave
a literal "${PORT:-8000}" unexpanded and crash uvicorn — reading os.environ here avoids
that entirely and works whether or not the platform injects PORT.
"""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
