#!/usr/bin/env bash
# Idempotent create/update of every Module 4 AWS resource (HANDOFF §8 W4). Schedule is created DISABLED.
# Usage: ALERT_EMAILS="a@x.com,b@y.com" service/deploy/up.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
source service/deploy/config.sh
check_account
TAGS_KV="Key=$TAG_KEY,Value=$TAG_VAL"

log "1. ECR repo $ECR_REPO"
if ! aws ecr describe-repositories --repository-names "$ECR_REPO" >/dev/null 2>&1; then
  aws ecr create-repository --repository-name "$ECR_REPO" --image-scanning-configuration scanOnPush=true \
    --tags "$TAGS_KV" >/dev/null
fi
aws ecr put-lifecycle-policy --repository-name "$ECR_REPO" --lifecycle-policy-text \
  '{"rules":[{"rulePriority":1,"description":"keep last 1","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":1},"action":{"type":"expire"}}]}' >/dev/null

log "2. build + push image ($ARCH)"
IMAGE_TAG="$(git rev-parse --short HEAD)-$(date -u +%Y%m%d%H%M%S)"
docker build --platform "linux/$ARCH" --provenance=false -f service/deploy/Dockerfile.lambda -t "$ECR_URI:$IMAGE_TAG" .
aws ecr get-login-password | docker login --username AWS --password-stdin "${ECR_URI%%/*}" >/dev/null
docker push -q "$ECR_URI:$IMAGE_TAG"
IMAGE_URI="$ECR_URI:$IMAGE_TAG"

log "3. DynamoDB $TABLE"
if ! aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  aws dynamodb create-table --table-name "$TABLE" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=kind,AttributeType=S AttributeName=generated_at,AttributeType=S \
    --key-schema AttributeName=kind,KeyType=HASH AttributeName=generated_at,KeyType=RANGE \
    --tags "$TAGS_KV" >/dev/null
  aws dynamodb wait table-exists --table-name "$TABLE"
fi
if [ "$(aws dynamodb describe-time-to-live --table-name "$TABLE" --query TimeToLiveDescription.TimeToLiveStatus --output text)" = "DISABLED" ]; then
  aws dynamodb update-time-to-live --table-name "$TABLE" --time-to-live-specification Enabled=true,AttributeName=ttl >/dev/null
fi

log "4. SNS $TOPIC"
aws sns create-topic --name "$TOPIC" --tags "$TAGS_KV" >/dev/null   # idempotent
IFS=',' read -ra EMAILS <<< "${ALERT_EMAILS:-}"
for email in "${EMAILS[@]}"; do
  email="$(echo "$email" | xargs)"; [ -z "$email" ] && continue
  if ! aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --query "Subscriptions[].Endpoint" --output text | tr '\t' '\n' | grep -qx "$email"; then
    aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email --notification-endpoint "$email" >/dev/null
    echo "subscribed $email (must click the confirmation email)"
  fi
done

log "5. IAM roles"
NEW_ROLE=0
if ! aws iam get-role --role-name "$LAMBDA_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$LAMBDA_ROLE" --tags "$TAGS_KV" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  NEW_ROLE=1
fi
aws iam attach-role-policy --role-name "$LAMBDA_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam put-role-policy --role-name "$LAMBDA_ROLE" --policy-name oracle-least-privilege --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\": \"Allow\", \"Action\": \"s3:ListBucket\", \"Resource\": \"arn:aws:s3:::$METRICS_BUCKET\"},
    {\"Effect\": \"Allow\", \"Action\": \"s3:GetObject\", \"Resource\": \"arn:aws:s3:::$METRICS_BUCKET/metrics/*\"},
    {\"Effect\": \"Allow\", \"Action\": [\"dynamodb:PutItem\", \"dynamodb:Query\", \"dynamodb:GetItem\"], \"Resource\": \"$TABLE_ARN\"},
    {\"Effect\": \"Allow\", \"Action\": \"sns:Publish\", \"Resource\": \"$TOPIC_ARN\"}
  ]}"
if ! aws iam get-role --role-name "$SCHEDULER_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$SCHEDULER_ROLE" --tags "$TAGS_KV" --assume-role-policy-document "{
    \"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"scheduler.amazonaws.com\"},
    \"Action\":\"sts:AssumeRole\",\"Condition\":{\"StringEquals\":{\"aws:SourceAccount\":\"$ACCOUNT_ID\"}}}]}" >/dev/null
  NEW_ROLE=1
fi
aws iam put-role-policy --role-name "$SCHEDULER_ROLE" --policy-name invoke-pipeline --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"$(fn_arn "$PIPELINE_FN")\"}]}"
[ "$NEW_ROLE" = 1 ] && { echo "waiting 15 s for new IAM roles to propagate"; sleep 15; }

log "6. CloudWatch log groups (7-day retention)"
for fn in "$API_FN" "$PIPELINE_FN"; do
  aws logs create-log-group --log-group-name "/aws/lambda/$fn" --tags "$TAG_KEY=$TAG_VAL" 2>/dev/null || true
  aws logs put-retention-policy --log-group-name "/aws/lambda/$fn" --retention-in-days 7
done

log "7. Lambda functions ($ARCH)"
ENV_VARS="Variables={ORACLE_STORE=dynamo,ORACLE_SOURCE=s3,METRICS_BUCKET=$METRICS_BUCKET,RESULTS_TABLE=$TABLE,ALERT_TOPIC_ARN=$TOPIC_ARN,DASHBOARD_URL=${DASHBOARD_URL:-https://cloud-oracle-ge5svfjhkafdnfipesqylt.streamlit.app},REPLAY_MODE=${REPLAY_MODE:-0},MPLCONFIGDIR=/tmp}"
deploy_fn() {  # name timeout handler
  local name=$1 timeout=$2 cmd=$3
  if ! aws lambda get-function --function-name "$name" >/dev/null 2>&1; then
    aws lambda create-function --function-name "$name" --package-type Image --code "ImageUri=$IMAGE_URI" \
      --role "$(role_arn "$LAMBDA_ROLE")" --architectures "$ARCH" --memory-size 1024 --timeout "$timeout" \
      --image-config "Command=$cmd" --environment "$ENV_VARS" --tags "$TAG_KEY=$TAG_VAL" >/dev/null
  else
    aws lambda update-function-code --function-name "$name" --image-uri "$IMAGE_URI" >/dev/null
    aws lambda wait function-updated-v2 --function-name "$name"
    aws lambda update-function-configuration --function-name "$name" --timeout "$timeout" --memory-size 1024 \
      --image-config "Command=$cmd" --environment "$ENV_VARS" >/dev/null
  fi
  aws lambda wait function-updated-v2 --function-name "$name"
  # cost guard; impossible on accounts whose concurrency limit is 10 (AWS keeps 10 unreserved)
  aws lambda put-function-concurrency --function-name "$name" --reserved-concurrent-executions 2 >/dev/null 2>&1 \
    || echo "WARN: reserved concurrency not set on $name (account limit too low); API throttling is the guard"
}
deploy_fn "$API_FN" 30 oracle_service.lambda_handlers.api_handler
deploy_fn "$PIPELINE_FN" 120 oracle_service.lambda_handlers.pipeline_handler

log "8. API Gateway HTTP API $API_NAME (5 rps, burst 10)"
API_ID=$(api_id)
if [ -z "$API_ID" ]; then
  API_ID=$(aws apigatewayv2 create-api --name "$API_NAME" --protocol-type HTTP --target "$(fn_arn "$API_FN")" \
    --tags "$TAG_KEY=$TAG_VAL" --query ApiId --output text)
fi
aws apigatewayv2 update-stage --api-id "$API_ID" --stage-name '$default' \
  --default-route-settings ThrottlingBurstLimit=10,ThrottlingRateLimit=5 >/dev/null
aws lambda add-permission --function-name "$API_FN" --statement-id apigw-invoke --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:$AWS_REGION:$ACCOUNT_ID:$API_ID/*" >/dev/null 2>&1 || true

log "9. EventBridge Scheduler $SCHEDULE (DISABLED; toggle with make -C service schedule-on/off)"
# Scheduler schedules in the default group can't carry tags; the name prefix identifies it.
if ! aws scheduler get-schedule --name "$SCHEDULE" >/dev/null 2>&1; then
  aws scheduler create-schedule --name "$SCHEDULE" --schedule-expression "rate(15 minutes)" \
    --flexible-time-window Mode=OFF --state DISABLED \
    --target "{\"Arn\":\"$(fn_arn "$PIPELINE_FN")\",\"RoleArn\":\"$(role_arn "$SCHEDULER_ROLE")\",\"Input\":\"{}\"}" >/dev/null
fi

log "done"
echo "API URL: $(api_url)"
echo "schedule: $(aws scheduler get-schedule --name "$SCHEDULE" --query State --output text)"
