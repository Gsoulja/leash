# Leash engine image: API (serving the built app), worker, migrations and the local fake platform.
# Build context is the repository root (the image needs the challenge pack in data/):
#   docker compose -f solution/docker-compose.yml build
FROM node:22-slim AS app
WORKDIR /repo/solution/app
COPY solution/app/package.json solution/app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY solution/contracts/ /repo/solution/contracts/
COPY solution/app/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /repo/solution/engine
COPY solution/engine/pyproject.toml solution/engine/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY solution/engine/ ./
RUN uv sync --frozen --no-dev
COPY data/ /repo/data/
COPY --from=app /repo/solution/app/dist /repo/solution/app/dist
ENV LEASH_DATA_DIR=/repo/data LEASH_APP_DIST=/repo/solution/app/dist \
    LEASH_EVENT_SCHEMA=/repo/data/schemas/authorization_event.schema.json
RUN useradd --create-home leash
USER leash
CMD ["leash-api"]
