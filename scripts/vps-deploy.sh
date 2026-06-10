#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is not available." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "Missing $project_dir/.env. Create it from .env.example first." >&2
  exit 1
fi

docker compose config --quiet
docker compose build bot
docker compose up -d
docker compose ps
