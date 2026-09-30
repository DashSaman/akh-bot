# akh-bot — lightweight modular monolith (internal namespace: akhbot)
FROM python:3.12-slim AS base

ARG GIT_SHA=unknown
ENV AKHBOT_GIT_SHA=${GIT_SHA} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && rm -rf /root/.cache

COPY app ./app
COPY templates ./templates
COPY static ./static
COPY config ./config

# non-root runtime user
RUN useradd --system --uid 10001 --no-create-home akhbot \
    && mkdir -p /data && chown -R akhbot:akhbot /srv /data
USER akhbot

ENV DATA_DIR=/data \
    BRAND_CONFIG=config/brand.yml

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

EXPOSE 8000
# graceful shutdown: uvicorn handles SIGTERM; docker stop --time 15
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "5"]
