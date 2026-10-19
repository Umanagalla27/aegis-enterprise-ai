# syntax=docker/dockerfile:1

# ---- Stage 1: build wheels in a throwaway image (compilers never reach production) ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build

COPY requirements-prod.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements-prod.txt \
    && /opt/venv/bin/python -m pip uninstall -y pip

# ---- Stage 2: minimal runtime image ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    WEB_CONCURRENCY=2

# Unprivileged user: a container escape or RCE does not land as root.
# pip is removed: the service never installs packages at runtime, and pip's vendored
# libraries (urllib3, msgpack, setuptools) are flagged by image scanners.
RUN groupadd --system --gid 10001 aegis \
    && useradd --system --uid 10001 --gid aegis --no-create-home aegis \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip* /usr/local/bin/pip*

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# Code stays root-owned: the app user can read it but cannot modify it
COPY src ./src
COPY eval ./eval
COPY data_platform ./data_platform
# The ETL endpoints write Parquet/SQLite output under data/
RUN mkdir -p /app/data/analytics && chown -R aegis:aegis /app/data

USER aegis
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# Gunicorn supervises Uvicorn workers: restarts crashed workers, graceful shutdown on SIGTERM
CMD ["sh", "-c", "exec gunicorn src.api.main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY} -b 0.0.0.0:${PORT} --timeout 60 --graceful-timeout 30 --access-logfile -"]
