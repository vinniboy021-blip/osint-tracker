# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --gid 10001 osint && useradd --uid 10001 --gid osint --no-create-home osint \
    && mkdir -p /data/evidence && chown osint:osint /data/evidence
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/app ./app
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir .; \
    else pip install --no-cache-dir .; fi
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
USER osint
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
