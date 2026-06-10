#!/usr/bin/env bash
set -u

section() {
  printf '\n===== %s =====\n' "$1"
}

section "System"
uname -a
cat /etc/os-release 2>/dev/null || true
uptime

section "Resources"
free -h 2>/dev/null || true
df -h /
nproc 2>/dev/null || true

section "Docker"
docker version 2>&1 || true
docker compose version 2>&1 || true
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1 || true

section "GitLab Runner"
systemctl is-enabled gitlab-runner 2>&1 || true
systemctl is-active gitlab-runner 2>&1 || true
systemctl status gitlab-runner --no-pager -n 20 2>&1 || true

section "Listening ports"
ss -lntup 2>&1 || true

section "LoogikaBot target"
if [ -d /opt/loogikabot ]; then
  ls -la /opt/loogikabot
else
  echo "/opt/loogikabot does not exist"
fi
