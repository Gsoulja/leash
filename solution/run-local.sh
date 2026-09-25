#!/usr/bin/env bash
# Start the whole Leash stack: by default against the local fake Viseca
# platform, or against the real (live) platform with --live.
#
# Local mode (default): forces TEAM_API_KEY and LEASH_BASE_URL to the
# fake-platform defaults on the command line, so a solution/.env set up
# for event day (real key, real LEASH_BASE_URL) can't leak into a local
# run — Compose lets shell env vars override .env, so this is safe even
# when .env exists.
#
# Live mode (--live): does NOT override TEAM_API_KEY/LEASH_BASE_URL, so
# solution/.env's real values take effect, and does not start the local
# fake platform — matching RUNBOOK.md's event-day command. As of writing,
# the live API's /v1/bootstrap reports data version saw26-hackaton-api,
# which the worker rejects (expects saw26) — --live currently fails at
# worker startup until that's resolved with the team.
#
# Usage:
#   solution/run-local.sh                # build, start, wait for health (fake platform)
#   solution/run-local.sh --check         # also run the connection check
#   solution/run-local.sh --live          # build, start against the real platform (.env)
#   solution/run-local.sh --live --check  # same, plus connection check (refuses non-local base URL without --live; see script)
#   solution/run-local.sh --down          # stop and remove containers
#   solution/run-local.sh --reset         # stop and drop the db volume (dev only)

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose_file="$script_dir/docker-compose.yml"

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

if [[ "$live" == false ]]; then
  export TEAM_API_KEY="fake-team-key"
  export LEASH_BASE_URL="http://fake:9000"
fi

compose() {
  if [[ "$live" == true ]]; then
    docker compose -f "$compose_file" "$@"
  else
    docker compose -f "$compose_file" --profile fake "$@"
  fi
}

# --down and --reset always target both profiles, so a leftover fake
# container from a previous local run gets cleaned up too, regardless
# of which mode is stopping it.
case "$action" in
  --down)
    docker compose -f "$compose_file" --profile fake down
    exit 0
    ;;
  --reset)
    echo "Dropping the local db volume (dev only)..."
    docker compose -f "$compose_file" --profile fake down -v
    exit 0
    ;;
esac

if [[ "$live" == true ]]; then
  echo "Starting db, migrate, api, worker against the LIVE Viseca platform (from solution/.env)..."
else
  echo "Starting db, migrate, fake, api, worker against the local fake platform..."
fi
compose up -d --build --wait

echo
echo "api  readyz:    $(curl -s localhost:8080/readyz)"
echo "worker readyz:  $(curl -s localhost:8081/readyz)"
echo
echo "Customer app:    http://localhost:8080/"
if [[ "$live" == false ]]; then
  echo "Fake platform:   http://localhost:9000/"
fi
echo "Worker health:   http://localhost:8081/healthz"
echo
echo "Logs:  docker compose -f $compose_file logs -f worker api"
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
      LEASH_BASE_URL=http://localhost:9000 TEAM_API_KEY=fake-team-key uv run python scripts/connection_check.py
    )
  fi
fi
