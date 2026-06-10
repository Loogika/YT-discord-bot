#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$project_dir/.env"
temp_file="$(mktemp "$project_dir/.env.XXXXXX")"

cleanup() {
  rm -f "$temp_file"
}
trap cleanup EXIT

read -rsp "Discord bot token: " discord_token
printf '\n'
read -rp "Discord guild ID (optional): " discord_guild_id
read -rp "Log level [INFO]: " log_level
read -rsp "Grafana admin password: " grafana_password
printf '\n'

log_level="${log_level:-INFO}"

if [[ -z "$discord_token" ]]; then
  echo "Discord bot token cannot be empty." >&2
  exit 1
fi

if [[ -z "$grafana_password" ]]; then
  echo "Grafana admin password cannot be empty." >&2
  exit 1
fi

if [[ "$discord_token" == *"'"* || "$grafana_password" == *"'"* ]]; then
  echo "Discord token and Grafana password cannot contain single quotes." >&2
  exit 1
fi

if [[ -n "$discord_guild_id" && ! "$discord_guild_id" =~ ^[0-9]+$ ]]; then
  echo "Discord guild ID must contain only digits." >&2
  exit 1
fi

case "$log_level" in
  DEBUG|INFO|WARNING|ERROR|CRITICAL) ;;
  *)
    echo "Log level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL." >&2
    exit 1
    ;;
esac

{
  printf "DISCORD_TOKEN='%s'\n" "$discord_token"
  printf "DISCORD_GUILD_ID='%s'\n" "$discord_guild_id"
  printf "LOG_LEVEL='%s'\n" "$log_level"
  printf "GRAFANA_ADMIN_PASSWORD='%s'\n" "$grafana_password"
} > "$temp_file"

chmod 600 "$temp_file"
mv -f "$temp_file" "$env_file"
trap - EXIT

echo "Updated $env_file with permissions 600."
