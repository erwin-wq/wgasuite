#!/usr/bin/env sh
set -eu

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

if ! command -v curl >/dev/null 2>&1; then
  printf "Missing required command: curl\n"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf "Missing required command: python3\n"
  exit 1
fi

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

response_body="$TMP_DIR/response.json"
response_headers="$TMP_DIR/headers.txt"

request_json() {
  method="$1"
  path="$2"
  data="${3:-}"

  if [ -n "$data" ]; then
    set +e
    status_code=$(curl -sS -X "$method" \
      -H "Content-Type: application/json" \
      -d "$data" \
      -D "$response_headers" \
      -o "$response_body" \
      -w "%{http_code}" \
      "$API_BASE_URL$path")
    curl_status=$?
    set -e
  else
    set +e
    status_code=$(curl -sS -X "$method" \
      -D "$response_headers" \
      -o "$response_body" \
      -w "%{http_code}" \
      "$API_BASE_URL$path")
    curl_status=$?
    set -e
  fi

  if [ "$curl_status" -ne 0 ]; then
    printf "Request failed: %s %s could not reach %s\n" "$method" "$path" "$API_BASE_URL"
    printf "Make sure the backend is running, then try again.\n"
    exit 1
  fi

  case "$status_code" in
    200|201)
      return 0
      ;;
    *)
      printf "Request failed: %s %s returned HTTP %s\n" "$method" "$path" "$status_code"
      printf "Response body:\n"
      cat "$response_body"
      printf "\n"
      exit 1
      ;;
  esac
}

json_get() {
  path="$1"
  python3 - "$path" "$response_body" <<'PY'
import json
import sys

path = sys.argv[1].split(".")
file_path = sys.argv[2]

with open(file_path, encoding="utf-8") as handle:
    value = json.load(handle)

for part in path:
    value = value[part]

print(value)
PY
}

assert_json_value() {
  path="$1"
  expected="$2"
  actual=$(json_get "$path")

  if [ "$actual" != "$expected" ]; then
    printf "Assertion failed for %s: expected %s, got %s\n" "$path" "$expected" "$actual"
    printf "Response body:\n"
    cat "$response_body"
    printf "\n"
    exit 1
  fi
}

printf "Running API smoke test against %s\n\n" "$API_BASE_URL"

printf "1. Checking backend health...\n"
request_json "GET" "/health"
assert_json_value "status" "ok"

timestamp="$(date +%Y%m%d%H%M%S)-$$"

printf "2. Creating organization...\n"
request_json "POST" "/api/v1/organizations" "{
  \"name\": \"Smoke Test Org $timestamp\",
  \"description\": \"Created by scripts/dev/smoke_api.sh\"
}"
organization_id=$(json_get "id")
printf "   organization_id=%s\n" "$organization_id"

printf "3. Creating assessment...\n"
request_json "POST" "/api/v1/assessments" "{
  \"organization_id\": \"$organization_id\",
  \"title\": \"Smoke assessment $timestamp\",
  \"scope_summary\": \"API smoke test scope\"
}"
assessment_id=$(json_get "id")
printf "   assessment_id=%s\n" "$assessment_id"

printf "4. Creating asset...\n"
request_json "POST" "/api/v1/assets" "{
  \"organization_id\": \"$organization_id\",
  \"name\": \"Smoke asset $timestamp\",
  \"asset_type\": \"saas\",
  \"identifier\": \"smoke-$timestamp\",
  \"description\": \"API smoke test asset\"
}"
asset_id=$(json_get "id")
printf "   asset_id=%s\n" "$asset_id"

printf "5. Creating finding with DREAD score...\n"
request_json "POST" "/api/v1/findings" "{
  \"assessment_id\": \"$assessment_id\",
  \"asset_id\": \"$asset_id\",
  \"title\": \"Smoke finding $timestamp\",
  \"description\": \"API smoke test finding\",
  \"status\": \"open\",
  \"mitigation\": \"Validate controls\",
  \"dread_score\": {
    \"damage\": 8,
    \"reproducibility\": 8,
    \"exploitability\": 7,
    \"affected_users\": 9,
    \"discoverability\": 8
  }
}"
finding_id=$(json_get "id")
assert_json_value "dread_score.total_score" "8.0"
assert_json_value "dread_score.risk_level" "Critical"
printf "   finding_id=%s total_score=8.0 risk_level=Critical\n" "$finding_id"

printf "6. Getting finding...\n"
request_json "GET" "/api/v1/findings/$finding_id"
assert_json_value "id" "$finding_id"
assert_json_value "dread_score.risk_level" "Critical"

printf "7. Patching DREAD score...\n"
request_json "PATCH" "/api/v1/findings/$finding_id" "{
  \"dread_score\": {
    \"damage\": 6,
    \"reproducibility\": 6,
    \"exploitability\": 6,
    \"affected_users\": 6,
    \"discoverability\": 6
  }
}"
assert_json_value "dread_score.total_score" "6.0"
assert_json_value "dread_score.risk_level" "High"

printf "\nAPI smoke test passed.\n"
