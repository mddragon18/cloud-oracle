#!/usr/bin/env bash
# service/deploy/schedule.sh on|off — only during integration windows / demo week.
set -euo pipefail
cd "$(dirname "$0")/../.."
source service/deploy/config.sh
check_account
case "${1:-}" in on) STATE=ENABLED ;; off) STATE=DISABLED ;; *) echo "usage: $0 on|off"; exit 2 ;; esac
aws scheduler update-schedule --name "$SCHEDULE" --schedule-expression "rate(15 minutes)" \
  --flexible-time-window Mode=OFF --state "$STATE" \
  --target "{\"Arn\":\"$(fn_arn "$PIPELINE_FN")\",\"RoleArn\":\"$(role_arn "$SCHEDULER_ROLE")\",\"Input\":\"{}\"}" >/dev/null
echo "$SCHEDULE: $(aws scheduler get-schedule --name "$SCHEDULE" --query State --output text)"
