#!/usr/bin/env bash
# service/deploy/replay.sh on|off — set REPLAY_MODE on both Lambdas, keep their other env vars, rerun the pipeline.
set -euo pipefail
cd "$(dirname "$0")/../.."
source service/deploy/config.sh
check_account
case "${1:-}" in on) VALUE=1 ;; off) VALUE=0 ;; *) echo "usage: $0 on|off"; exit 2 ;; esac
for fn in "$API_FN" "$PIPELINE_FN"; do
  env_json=$(aws lambda get-function-configuration --function-name "$fn" --query Environment --output json)
  env_json=$(VALUE="$VALUE" python3 -c 'import json,os,sys; e=json.load(sys.stdin); e["Variables"]["REPLAY_MODE"]=os.environ["VALUE"]; print(json.dumps(e))' <<<"$env_json")
  aws lambda update-function-configuration --function-name "$fn" --environment "$env_json" >/dev/null
  aws lambda wait function-updated --function-name "$fn"
  echo "$fn: REPLAY_MODE=$VALUE"
done
OUT=$(mktemp)
aws lambda invoke --function-name "$PIPELINE_FN" --cli-read-timeout 300 --cli-binary-format raw-in-base64-out --payload '{}' "$OUT" >/dev/null
cat "$OUT"; echo
if grep -q errorMessage "$OUT"; then rm -f "$OUT"; exit 1; fi
rm -f "$OUT"
