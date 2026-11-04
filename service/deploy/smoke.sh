#!/usr/bin/env bash
# Hit every endpoint of the deployed API; check status codes and JSON keys. Exit 1 on any failure.
set -uo pipefail
cd "$(dirname "$0")/../.."
source service/deploy/config.sh
URL="${API_URL:-$(api_url)}"
[ -n "$URL" ] || { echo "no API found (run up.sh)"; exit 1; }
echo "API: $URL"
FAIL=0
check() {  # method path keys... ; body via $BODY
  local method=$1 path=$2; shift 2
  local out code
  out=$(curl -s -w '\n%{http_code}' -X "$method" "$URL$path" ${BODY:+-H 'content-type: application/json' -d "$BODY"})
  code=${out##*$'\n'}; out=${out%$'\n'*}
  if [ "$code" = 200 ] && python3 -c 'import json,sys; d=json.loads(sys.argv[1]); missing=[k for k in sys.argv[2:] if k not in d]; sys.exit(1 if missing else 0)' "$out" "$@"; then
    echo "PASS $method $path"
  else
    echo "FAIL $method $path -> $code ${out:0:200}"; FAIL=1
  fi
}
check GET /health status
check GET /forecast/latest generated_at series exhaustion_at accuracy
check GET /plan/latest generated_at options recommendation exhaustion_at
check GET "/history?days=7" plans
check GET "/metrics/recent?hours=24" rows
BODY='{"expected_rpm": 500}' check POST /plan options peak_requests_per_min
BODY='{"expected_rpm": 5000}' check POST /plan options peak_requests_per_min
exit $FAIL
