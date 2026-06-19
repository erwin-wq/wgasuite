#!/usr/bin/env sh
set -u

failures=0

check_command() {
  name="$1"
  command_name="$2"
  version_command="$3"

  if command -v "$command_name" >/dev/null 2>&1; then
    version_output=$(sh -c "$version_command" 2>&1)
    printf "OK   %-16s %s\n" "$name" "$version_output"
  else
    printf "MISS %-16s command not found: %s\n" "$name" "$command_name"
    failures=$((failures + 1))
  fi
}

printf "Checking local development environment...\n\n"

check_command "python3" "python3" "python3 --version"
check_command "docker" "docker" "docker --version"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  printf "OK   %-16s %s\n" "docker compose" "$(docker compose version)"
else
  printf "MISS %-16s command not available: docker compose\n" "docker compose"
  failures=$((failures + 1))
fi

check_command "node" "node" "node --version"
check_command "npm" "npm" "npm --version"

printf "\n"

if [ "$failures" -gt 0 ]; then
  printf "Environment check failed: %s required tool(s) missing.\n" "$failures"
  printf "Install missing tools outside this script, then run this check again.\n"
  exit 1
fi

printf "Environment check passed.\n"
