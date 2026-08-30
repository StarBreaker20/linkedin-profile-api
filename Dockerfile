FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

EXPOSE 8000
# Entrypoint resolves $PORT in Python (no shell needed) — see app/__main__.py.
# Respects $PORT on hosts like Render/Railway/Fly; defaults to 8000 locally.
CMD ["python", "-m", "app"]
