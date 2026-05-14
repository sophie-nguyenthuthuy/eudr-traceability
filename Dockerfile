FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libgdal-dev \
        gdal-bin \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps in a layer that's cached independently of the source.
# We stub out src/eudr/__init__.py so `pip install -e .` can resolve the
# package metadata; the real source is COPYed in below.
COPY pyproject.toml ./
RUN mkdir -p src/eudr && touch src/eudr/__init__.py && \
    pip install --upgrade pip && \
    pip install -e ".[dev]"

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY tests ./tests

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app && \
    chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "eudr.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
