# Module 4 AWS names — single source (HANDOFF §9). Sourced by up.sh / down.sh / smoke.sh / schedule.sh.
export AWS_PROFILE="${AWS_PROFILE:-oracle-m4}"
export AWS_REGION="ap-south-1" AWS_DEFAULT_REGION="ap-south-1" AWS_PAGER=""
ACCOUNT_ID="149236595048"
METRICS_BUCKET="cloud-oracle-metrics-149236595048"   # owned by Member 1, read-only for us
ARCH="arm64"                                          # Lambda architecture == native Apple Silicon build

ECR_REPO="oracle-service"
API_FN="oracle-api"
PIPELINE_FN="oracle-pipeline"
API_NAME="oracle-api"
TABLE="oracle-results"
TOPIC="oracle-alerts"
SCHEDULE="oracle-pipeline-15min"
LAMBDA_ROLE="oracle-lambda-role"
SCHEDULER_ROLE="oracle-scheduler-role"

TAG_KEY="project" TAG_VAL="oracle"
ECR_URI="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO"
TOPIC_ARN="arn:aws:sns:$AWS_REGION:$ACCOUNT_ID:$TOPIC"
TABLE_ARN="arn:aws:dynamodb:$AWS_REGION:$ACCOUNT_ID:table/$TABLE"
fn_arn() { echo "arn:aws:lambda:$AWS_REGION:$ACCOUNT_ID:function:$1"; }
role_arn() { echo "arn:aws:iam::$ACCOUNT_ID:role/$1"; }
api_id() { aws apigatewayv2 get-apis --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text | grep -v None || true; }
api_url() { local id; id=$(api_id); [ -n "$id" ] && echo "https://$id.execute-api.$AWS_REGION.amazonaws.com"; }

check_account() {
  local acct; acct=$(aws sts get-caller-identity --query Account --output text)
  [ "$acct" = "$ACCOUNT_ID" ] || { echo "wrong AWS account: $acct (expected $ACCOUNT_ID)" >&2; exit 1; }
}
current_replay() {  # the deployed REPLAY_MODE; 0 only if the Lambda or the variable doesn't exist yet
  local v
  v=$(aws lambda get-function-configuration --function-name "$PIPELINE_FN" \
    --query Environment.Variables.REPLAY_MODE --output text 2>&1) || case "$v" in
      *ResourceNotFound*) v=0 ;;
      *) echo "cannot read REPLAY_MODE: $v" >&2; return 1 ;;
    esac
  [ "$v" = None ] && v=0
  echo "$v"
}
log() { printf '\n== %s\n' "$*"; }
