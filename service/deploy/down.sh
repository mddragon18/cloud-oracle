#!/usr/bin/env bash
# Delete Module 4 AWS resources in reverse order. --keep-data keeps the DynamoDB table and SNS topic.
# Never touches the metrics bucket (Member 1's). DRY_RUN=1 prints every delete and runs none.
set -euo pipefail
cd "$(dirname "$0")/../.."
source service/deploy/config.sh
check_account
KEEP_DATA=0; [ "${1:-}" = "--keep-data" ] && KEEP_DATA=1
DRY_RUN="${DRY_RUN:-0}"
gone() {
  if [ "$DRY_RUN" = 1 ]; then echo "would run: $*"; return; fi
  "$@" >/dev/null 2>&1 && echo "deleted: ${*: -1}" || echo "absent:  ${*: -1}"
}
quiet() {  # prerequisite deletes: absent is fine
  if [ "$DRY_RUN" = 1 ]; then echo "would run: $*"; return; fi
  "$@" >/dev/null 2>&1 || true
}

log "schedule first"
gone aws scheduler delete-schedule --name "$SCHEDULE"
quiet aws iam delete-role-policy --role-name "$SCHEDULER_ROLE" --policy-name invoke-pipeline
gone aws iam delete-role --role-name "$SCHEDULER_ROLE"

log "API Gateway"
API_ID=$(api_id)
[ -n "$API_ID" ] && gone aws apigatewayv2 delete-api --api-id "$API_ID" || echo "absent:  $API_NAME"

log "Lambda + logs"
for fn in "$API_FN" "$PIPELINE_FN"; do
  gone aws lambda delete-function --function-name "$fn"
  gone aws logs delete-log-group --log-group-name "/aws/lambda/$fn"
done

log "IAM lambda role"
quiet aws iam detach-role-policy --role-name "$LAMBDA_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
quiet aws iam delete-role-policy --role-name "$LAMBDA_ROLE" --policy-name oracle-least-privilege
gone aws iam delete-role --role-name "$LAMBDA_ROLE"

if [ "$KEEP_DATA" = 0 ]; then
  log "data (pass --keep-data to keep)"
  gone aws sns delete-topic --topic-arn "$TOPIC_ARN"
  gone aws dynamodb delete-table --table-name "$TABLE"
else
  log "kept: $TABLE, $TOPIC"
fi

log "ECR (images included)"
gone aws ecr delete-repository --repository-name "$ECR_REPO" --force

[ "$DRY_RUN" = 1 ] && { echo "dry run: nothing deleted"; exit 0; }
log "left tagged $TAG_KEY=$TAG_VAL (expect only Member 1's resources, plus table/topic with --keep-data):"
aws resourcegroupstaggingapi get-resources --tag-filters "Key=$TAG_KEY,Values=$TAG_VAL" \
  --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '\t' '\n'
