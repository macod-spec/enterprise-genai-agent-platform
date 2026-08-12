FROM python:3.13-slim AS builder
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app app \
    && mkdir -p /var/lib/platform && chown app:app /var/lib/platform
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --no-index --find-links=/wheels \
        enterprise-genai-agent-platform \
    && /usr/local/bin/python -m pip uninstall --yes pip setuptools wheel \
    && /opt/venv/bin/pip uninstall --yes pip setuptools wheel \
    && rm -rf /wheels /root/.cache
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]
CMD ["uvicorn", "enterprise_genai_platform.gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
