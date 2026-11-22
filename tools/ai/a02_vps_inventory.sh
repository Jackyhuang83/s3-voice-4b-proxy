#!/usr/bin/env bash
# GDGS A02: read-only, sanitized VPS inventory. No credentials, hostnames or IPs.
set -u
export LC_ALL=C
field() { printf '%s=%s\n' "$1" "$2"; }
directory() { if test -d "$1"; then printf present; else printf absent; fi; }

printf '%s\n' 'S3_VOICE_AI_A02_INVENTORY_V1'
field "timestamp_utc" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
field "scope" "host_where_command_is_executed"
if test -r /etc/os-release; then
  field "os_id" "$(awk -F= '$1=="ID" {gsub(/"/, "", $2);print $2;exit}' /etc/os-release)"
  field "os_version_id" "$(awk -F= '$1=="VERSION_ID" {gsub(/"/, "", $2);print $2;exit}' /etc/os-release)"
else
  field "os_id" "unknown"
  field "os_version_id" "unknown"
fi
field "arch" "$(uname -m)"
field "kernel" "$(uname -r)"
if command -v getconf >/dev/null 2>&1; then
  field "cpus_online" "$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf unknown)"
else
  field "cpus_online" "unknown"
fi
if test -r /proc/meminfo; then
  field "memory_total_kib" "$(awk '/^MemTotal:/ {print $2;exit}' /proc/meminfo)"
  field "memory_available_kib" "$(awk '/^MemAvailable:/ {print $2;exit}' /proc/meminfo)"
else
  field "memory_total_kib" "unknown"
  field "memory_available_kib" "unknown"
fi
for folder in /opt /var/lib/docker; do
  if test -d "$folder"; then
    remaining="$(df -Pk "$folder" 2>/dev/null | awk 'NR==2 {print $4}')"
    if test -z "$remaining"; then remaining=unknown; fi
    field "disk_available_kib_$(basename "$folder")" "$remaining"
  fi
done
if command -v docker >/dev/null 2>&1; then
  field "docker_cli" "present"
  field "docker_engine_version" "$(docker version --format '{{.Server.Version}}' 2>/dev/null || printf inaccessible)"
  field "docker_compose_version" "$(docker compose version --short 2>/dev/null || printf inaccessible)"
  containers="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"
  known="$(printf '%s\n' "$containers" | grep -E '^(homesphere($|-)|miniprobe($|-)|qms-postgres$|media-bridge$|cloudflared($|-)|s3-voice-ai($|-)|xiaozhi($|-))' | sort | paste -sd, - || true)"
  if test -z "$known"; then known=none_or_inaccessible; fi
  field "known_running_containers" "$known"
else
  field "docker_cli" "absent"
  field "docker_engine_version" "unknown"
  field "docker_compose_version" "unknown"
  field "known_running_containers" "unknown"
fi
if command -v ss >/dev/null 2>&1; then
  sockets="$(ss -H -lnt 2>/dev/null || true)"
else
  sockets=""
fi
for port in 80 443 8000 8003 8080 12333 28888 18000 18003 18080; do
  if test -z "$sockets"; then
    status=unknown
  elif printf '%s\n' "$sockets" | awk '{print $4}' | grep -Eq "(^|:)$port$"; then
    status=listening
  else
    status=no_listener_seen
  fi
  field "tcp_port_$port" "$status"
done
field "homesphere_dir" "$(directory /opt/homesphere)"
field "miniprobe_dir" "$(directory /opt/miniprobe-docker)"
field "s3_voice_ai_dir" "$(directory /opt/s3-voice-ai)"
printf '%s\n' 'A02_INVENTORY_END'
