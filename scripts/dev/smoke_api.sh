#!/usr/bin/env sh
set -eu

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
SMOKE_API_EMAIL="${SMOKE_API_EMAIL:-admin@example.local}"
SMOKE_API_PASSWORD="${SMOKE_API_PASSWORD:-ChangeMe123!}"
AUTH_TOKEN=""

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
    if [ -n "$AUTH_TOKEN" ]; then
      set +e
      status_code=$(curl -sS -X "$method" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $AUTH_TOKEN" \
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
        -H "Content-Type: application/json" \
        -d "$data" \
        -D "$response_headers" \
        -o "$response_body" \
        -w "%{http_code}" \
        "$API_BASE_URL$path")
      curl_status=$?
      set -e
    fi
  else
    if [ -n "$AUTH_TOKEN" ]; then
      set +e
      status_code=$(curl -sS -X "$method" \
        -H "Authorization: Bearer $AUTH_TOKEN" \
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

assert_json_number_greater_than() {
  path="$1"
  minimum="$2"
  python3 - "$path" "$minimum" "$response_body" <<'PY'
import json
import sys

path = sys.argv[1].split(".")
minimum = float(sys.argv[2])
file_path = sys.argv[3]

with open(file_path, encoding="utf-8") as handle:
    value = json.load(handle)

for part in path:
    value = value[part]

if float(value) <= minimum:
    raise SystemExit(f"Assertion failed for {'.'.join(path)}: expected > {minimum}, got {value}")
PY
}

assert_json_array_length() {
  expected="$1"
  python3 - "$expected" "$response_body" <<'PY'
import json
import sys

expected = int(sys.argv[1])
file_path = sys.argv[2]

with open(file_path, encoding="utf-8") as handle:
    value = json.load(handle)

actual = len(value)
if actual != expected:
    raise SystemExit(f"Assertion failed for array length: expected {expected}, got {actual}")
PY
}

assert_report_has_mock_finding() {
  python3 - "$response_body" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    report = json.load(handle)

if not any(
    finding["title"].startswith("[Mock Google Workspace]")
    for finding in report.get("findings", [])
):
    raise SystemExit("Report did not contain a mock Google Workspace finding.")
PY
}

printf "Running API smoke test against %s\n\n" "$API_BASE_URL"

printf "1. Checking backend health...\n"
request_json "GET" "/health"
assert_json_value "status" "ok"

printf "2. Logging in as development user...\n"
request_json "POST" "/api/v1/auth/login" "{
  \"email\": \"$SMOKE_API_EMAIL\",
  \"password\": \"$SMOKE_API_PASSWORD\"
}"
AUTH_TOKEN=$(json_get "access_token")
if [ -z "$AUTH_TOKEN" ]; then
  printf "Login did not return an access token.\n"
  exit 1
fi
printf "   authenticated=%s\n" "$SMOKE_API_EMAIL"

printf "3. Checking Google Workspace check catalog...\n"
request_json "GET" "/api/v1/connectors/google-workspace/checks"
assert_json_array_length "7"
printf "   checks=7\n"

timestamp="$(date +%Y%m%d%H%M%S)-$$"

printf "4. Creating customer...\n"
request_json "POST" "/api/v1/customers" "{
  \"name\": \"Smoke Customer $timestamp\",
  \"slug\": \"smoke-customer-$timestamp\",
  \"contact_name\": \"Smoke Tester\",
  \"contact_email\": \"smoke@example.local\",
  \"status\": \"active\",
  \"notes\": \"Created by scripts/dev/smoke_api.sh\"
}"
customer_id=$(json_get "id")
printf "   customer_id=%s\n" "$customer_id"

printf "5. Creating organization...\n"
request_json "POST" "/api/v1/organizations" "{
  \"name\": \"Smoke Test Org $timestamp\",
  \"description\": \"Created by scripts/dev/smoke_api.sh\",
  \"customer_id\": \"$customer_id\"
}"
organization_id=$(json_get "id")
assert_json_value "customer_id" "$customer_id"
printf "   organization_id=%s\n" "$organization_id"

printf "6. Configuring Google Workspace connector metadata...\n"
request_json "POST" "/api/v1/organizations/$organization_id/connector-configs/google-workspace" "{
  \"display_name\": \"Smoke Google Workspace\",
  \"primary_domain\": \"smoke.example.local\",
  \"admin_subject_email\": \"admin@smoke.example.local\",
  \"auth_method\": \"service_account_domain_wide_delegation\",
  \"status\": \"configured\",
  \"notes\": \"Smoke test metadata only; no secrets stored.\"
}"
connector_config_id=$(json_get "id")
assert_json_value "connector_type" "google_workspace"
assert_json_value "status" "configured"
printf "   connector_config_id=%s\n" "$connector_config_id"

printf "7. Checking connector test placeholder...\n"
request_json "POST" "/api/v1/connector-configs/$connector_config_id/test"
assert_json_value "status" "not_implemented"
printf "   connector_test_status=not_implemented\n"

printf "8. Creating assessment...\n"
request_json "POST" "/api/v1/assessments" "{
  \"organization_id\": \"$organization_id\",
  \"title\": \"Smoke assessment $timestamp\",
  \"scope_summary\": \"API smoke test scope\"
}"
assessment_id=$(json_get "id")
printf "   assessment_id=%s\n" "$assessment_id"

printf "9. Creating asset...\n"
request_json "POST" "/api/v1/assets" "{
  \"organization_id\": \"$organization_id\",
  \"name\": \"Smoke asset $timestamp\",
  \"asset_type\": \"saas\",
  \"identifier\": \"smoke-$timestamp\",
  \"description\": \"API smoke test asset\"
}"
asset_id=$(json_get "id")
printf "   asset_id=%s\n" "$asset_id"

printf "10. Creating finding with DREAD score...\n"
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

printf "11. Getting finding...\n"
request_json "GET" "/api/v1/findings/$finding_id"
assert_json_value "id" "$finding_id"
assert_json_value "dread_score.risk_level" "Critical"

printf "12. Patching DREAD score...\n"
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

printf "13. Running mock Google Workspace scan...\n"
request_json "POST" "/api/v1/assessments/$assessment_id/scan-runs/google-workspace-mock"
scan_run_id=$(json_get "id")
assert_json_value "status" "completed"
assert_json_number_greater_than "findings_created" "0"
printf "   scan_run_id=%s findings_created=%s\n" "$scan_run_id" "$(json_get "findings_created")"

printf "14. Checking report contains mock scan findings...\n"
request_json "GET" "/api/v1/assessments/$assessment_id/report"
assert_json_number_greater_than "total_findings" "1"
assert_report_has_mock_finding

printf "\nAPI smoke test passed.\n"
