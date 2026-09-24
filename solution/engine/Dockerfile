# Leash engine image: API (serving the built app), worker, migrations and the local fake platform.
#
# Base images are pinned by digest, not by tag (LEASH-141): a tag is a moving target, so "the same
# Dockerfile" would otherwise build a different image next week and the thing we tested is not the thing
# we ship. Updates come through reviewed automation (.github/dependabot.yml), never by drift.
# `tests/test_supply_chain.py` fails if any FROM or COPY --from loses its digest.
# Build context is the repository root (the image needs the challenge pack in data/):
#   docker compose -f solution/docker-compose.yml build
# LEASH-151: the frontend is always rebuilt inside the image and stamped with APP_REVISION, so the
# bundle being served can be checked against the image that was deployed. dist/ is never copied in from
# the build context and never mounted at run time; readiness refuses a bundle whose stamp disagrees.
ARG APP_REVISION=dev
FROM node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS app
ARG APP_REVISION
ENV APP_REVISION=$APP_REVISION
WORKDIR /repo/solution/app
COPY solution/app/package.json solution/app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY solution/contracts/ /repo/solution/contracts/
COPY solution/app/ ./
RUN rm -rf dist && npm run build

FROM python:3.14-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2
ARG APP_REVISION
COPY --from=ghcr.io/astral-sh/uv:0.8@sha256:1d31be550ff927957472b2a491dc3de1ea9b5c2d319a9cea5b6a48021e2990a6 /uv /usr/local/bin/uv
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
    LEASH_EVENT_SCHEMA=/repo/data/schemas/authorization_event.schema.json \
    LEASH_APP_REVISION=$APP_REVISION
RUN useradd --create-home leash
USER leash
CMD ["leash-api"]
