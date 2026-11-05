# Build context: this directory.
#
#   docker build -t ediarum-index .
#
# Ignore rules: .dockerignore.

# --- build: the virtualenv -----------------------------------------------------
FROM python:3.13-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-dev --no-install-project

# Then the package itself.
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-cache --no-dev --no-editable

# --- runtime: no uv -----------------------------------------------------------
FROM python:3.13-slim

# mariadb-dump: the backup `ediarum-index migrate` writes before pending migrations
RUN apt-get update \
    && apt-get install -y --no-install-recommends mariadb-client \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=build /opt/venv /opt/venv

# The XML sources and the database are NOT baked in — they are mounted or
# reached at runtime (see docker-compose.yml). `serve` migrates the database
# before it starts the API, after a backup into $BACKUP_DIR if anything is
# pending.
EXPOSE 8000
CMD ["ediarum-index", "serve", "--host", "0.0.0.0", "--port", "8000"]
