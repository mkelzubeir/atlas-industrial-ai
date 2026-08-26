# Atlas backend — container image for a hosted deployment.
#
# Deliberately boring: a slim Python base, dependencies installed as their own
# layer so code changes do not re-resolve them, and a non-root user.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dependencies first: this layer is cached until pyproject.toml changes.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY seed ./seed

# The SQLite file lives here. On a host without a persistent volume the
# container is ephemeral, which is fine -- ATLAS_SEED_ON_STARTUP rebuilds the
# synthetic data on boot, so every restart is a clean, known demo state.
ENV ATLAS_DATABASE_URL=sqlite:////srv/data/atlas.db \
    ATLAS_SEED_ON_STARTUP=true \
    ATLAS_DEMO_MODE=true \
    PORT=8000

RUN mkdir -p /srv/data && useradd --create-home --uid 10001 atlas \
    && chown -R atlas:atlas /srv
USER atlas

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
