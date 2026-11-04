#!/usr/bin/env bash
# Tear down the experiment resources created by aws-up.sh: instance + SG.
# Keeps (all free, recreated by up.sh): key pair, instance profile/role,
# S3 bucket, budget. `aws-cost` check afterwards if unsure.
set -euo pipefail

REGION=${REGION:-ap-south-1}
SG_NAME=oracle-sg

if [ -f /tmp/oracle-instance-id ]; then
    INSTANCE_ID=$(cat /tmp/oracle-instance-id)
    aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
    echo "terminating $INSTANCE_ID"
    rm -f /tmp/oracle-instance-id /tmp/oracle-instance-dns
else
    # fallback: anything tagged project=oracle that is still running
    IDS=$(aws ec2 describe-instances --region "$REGION" \
        --filters "Name=tag:project,Values=oracle" "Name=instance-state-name,Values=running,pending" \
        --query 'Reservations[].Instances[].InstanceId' --output text)
    [ -n "$IDS" ] && aws ec2 terminate-instances --instance-ids $IDS --region "$REGION" \
        && echo "terminated: $IDS"
fi

SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$SG_NAME" \
        --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
if [ -n "${SG_ID:-}" ]; then
    sleep 20   # wait for termination to release the SG reference
    aws ec2 delete-security-group --group-id "$SG_ID" --region "$REGION" \
        || echo "SG $SG_ID not deletable yet (instance still terminating) — rerun down.sh"
fi

echo
echo "remaining project=oracle resources (should be only S3 bucket + budget + role):"
aws ec2 describe-instances --region "$REGION" --filters Name=instance-state-name,Values=running \
    --query "Reservations[].Instances[?Tags[?Value=='oracle']].InstanceId" --output text || true
