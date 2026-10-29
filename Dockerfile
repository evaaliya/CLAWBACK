# Clawback public demo image — Python only (no Node/Playwright).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/clawback.db \
    CACHE_DIR=/data/cache \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system clawback \
    && useradd --system --gid clawback --home-dir /app --shell /usr/sbin/nologin clawback \
    && mkdir -p /data /app \
    && chown -R clawback:clawback /data /app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=clawback:clawback app/ app/
COPY --chown=clawback:clawback demo/ demo/
COPY --chown=clawback:clawback jobs/ jobs/
COPY --chown=clawback:clawback scripts/ scripts/

USER clawback

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -sf http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]
