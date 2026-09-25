#!/usr/bin/env bash
# Start the whole Leash stack: by default against the local fake Viseca
# platform, or against the real (live) platform with --live.
#
# Local mode (default): runs as Compose project `leash-local` with
# docker-compose.local.yml on top, exactly as RUNBOOK.md does. The override
# pins every service to the fake platform (so a solution/.env set up for
# event day can't redirect a local run), turns on the assistant's local
# simulation (LEASH_SIMULATION=1, which the chat's demo-task picker needs),
# and keeps the fake platform's state in output/local-platform-state.
# `leash-local` has its own database volume, separate from live mode's.
# The assistant reads with OpenRouter by default: set OPENROUTER_API_KEY in
# solution/.env, or run with LEASH_ASSISTANT_MODEL=offline for a rehearsal.
#
# Live mode (--live): no override file, so solution/.env's real
# TEAM_API_KEY/LEASH_BASE_URL take effect, and no local fake platform — matching RUNBOOK.md's event-day command. As of writing,
# the live API's /v1/bootstrap reports data version saw26-hackaton-api,
# which the worker rejects (expects saw26) — --live currently fails at
# worker startup until that's resolved with the team.
#
# Usage:
#   solution/run-local.sh                # build, start, wait for health (fake platform)
#   solution/run-local.sh --check         # also run the connection check
#   solution/run-local.sh --live          # build, start against the real platform (.env)
#   solution/run-local.sh --live --check  # same, plus connection check (refuses non-local base URL without --live; see script)
#   solution/run-local.sh --down          # stop and remove containers (local and live)
#   solution/run-local.sh --reset         # stop and drop the local db volume (dev only)
#
# Ports follow the same variables as the compose file (LEASH_API_PORT,
# LEASH_WORKER_HEALTH_PORT, LEASH_ASSISTANT_PORT, LEASH_FAKE_PORT).

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose_file="$script_dir/docker-compose.yml"
local_file="$script_dir/docker-compose.local.yml"
local_project="leash-local"

live=false
check=false
action=""

for arg in "$@"; do
  case "$arg" in
    --live) live=true ;;
    --check) check=true ;;
    --down|--reset) action="$arg" ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

api_port="${LEASH_API_PORT:-8080}"
worker_port="${LEASH_WORKER_HEALTH_PORT:-8081}"
assistant_port="${LEASH_ASSISTANT_PORT:-8100}"
fake_port="${LEASH_FAKE_PORT:-9000}"

local_compose() {
  docker compose -p "$local_project" -f "$compose_file" -f "$local_file" --profile fake "$@"
}

compose() {
  if [[ "$live" == true ]]; then
    docker compose -f "$compose_file" "$@"
  else
    local_compose "$@"
  fi
}

case "$action" in
  --down)
    # Both stacks, so whichever mode last ran gets stopped. The live
    # project also includes the fake profile, to clean up containers left
    # by older versions of this script, which ran local mode under it.
    local_compose down
    docker compose -f "$compose_file" --profile fake down
    exit 0
    ;;
  --reset)
    echo "Dropping the local db volume (dev only)..."
    local_compose down -v
    exit 0
    ;;
esac

if [[ "$live" == true ]]; then
  echo "Starting db, migrate, api, worker, assistant against the LIVE Viseca platform (from solution/.env)..."
else
  echo "Starting db, migrate, fake, api, worker, assistant against the local fake platform..."
fi
compose up -d --build --wait

echo
echo "api  readyz:       $(curl -s "localhost:$api_port/readyz")"
echo "worker readyz:     $(curl -s "localhost:$worker_port/readyz")"
echo "assistant healthz: $(curl -s "localhost:$assistant_port/healthz")"
echo
echo "Customer app:    http://localhost:$api_port/"
if [[ "$live" == false ]]; then
  echo "Fake platform:   http://localhost:$fake_port/"
fi
echo "Worker health:   http://localhost:$worker_port/healthz"
echo
if [[ "$live" == true ]]; then
  echo "Logs:  docker compose -f $compose_file logs -f worker api assistant"
else
  echo "Logs:  docker compose -p $local_project -f $compose_file -f $local_file logs -f worker api assistant"
fi
echo "Stop:  $0 --down"

if [[ "$check" == true ]]; then
  echo
  echo "Running connection check..."
  if [[ "$live" == true ]]; then
    # connection_check.py reads TEAM_API_KEY/LEASH_BASE_URL straight from the
    # environment (VisecaClient.from_env), unlike Compose it does not read
    # solution/.env itself, so export them here.
    (
      set -a
      # shellcheck disable=SC1090
      source "$script_dir/.env"
      set +a
      cd "$script_dir/engine"
      uv run python scripts/connection_check.py --live
    )
  else
    (
      cd "$script_dir/engine"
      LEASH_BASE_URL="http://localhost:$fake_port" TEAM_API_KEY=fake-team-key uv run python scripts/connection_check.py
    )
  fi
fi
