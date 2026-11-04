#!/usr/bin/env bash
# Bring up the real-AWS experiment: one t3.micro in ap-south-1 running the
# docker stack (3 app replicas behind nginx on :8090, C1 collector inside),
# uploading metrics.csv to S3 via the instance profile. Tagged project=oracle.
# Everything aws-up.sh creates is torn down by aws-down.sh.
#
# Locust runs from your laptop afterwards (see "NEXT" output below).
set -euo pipefail

REGION=${REGION:-ap-south-1}
BUCKET=${BUCKET:-cloud-oracle-metrics-149236595048}
KEYPAIR=${KEYPAIR:-oracle-key}
SG_NAME=oracle-sg
ROLE=oracle-ec2-role
PROFILE=oracle-ec2
REPO=https://github.com/mddragon18/cloud-oracle.git

command -v aws >/dev/null || { echo "need aws cli"; exit 1; }

# --- EC2 key pair (kept by down.sh; free) -----------------------------------
if [ ! -f "$HOME/.ssh/$KEYPAIR.pem" ]; then
    mkdir -p "$HOME/.ssh"
    aws ec2 create-key-pair --key-name "$KEYPAIR" --region "$REGION" \
        --query 'KeyMaterial' --output text > "$HOME/.ssh/$KEYPAIR.pem"
    chmod 600 "$HOME/.ssh/$KEYPAIR.pem"
    echo "created key pair $KEYPAIR -> ~/.ssh/$KEYPAIR.pem"
fi

# --- instance profile: S3 write to the metrics bucket ------------------------
if ! aws iam get-instance-profile --instance-profile-name "$PROFILE" \
        --query 'InstanceProfile' >/dev/null 2>&1; then
    aws iam create-role --role-name "$ROLE" \
        --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    aws iam put-role-policy --role-name "$ROLE" --policy-name s3-metrics \
        --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:PutObject\",\"s3:GetObject\"],\"Resource\":[\"arn:aws:s3:::$BUCKET\",\"arn:aws:s3:::$BUCKET/*\"]}]}"
    aws iam create-instance-profile --instance-profile-name "$PROFILE"
    aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE" --role-name "$ROLE"
    echo "created instance profile $PROFILE (s3 rw on $BUCKET); sleeping 10s for propagation"
    sleep 10
fi

# --- security group: only :8090 for the load generator ----------------------
if ! aws ec2 describe-security-groups --filters Name=group-name,Values="$SG_NAME" \
        --query 'SecurityGroups[0].GroupId' --output text | grep -q '^sg-'; then
    VPC=$(aws ec2 describe-vpcs --query 'Vpcs[0].VpcId' --output text)
    aws ec2 create-security-group --group-name "$SG_NAME" \
        --description "cloud-oracle experiment" --vpc-id "$VPC"
    aws ec2 authorize-security-group-ingress --group-name "$SG_NAME" \
        --protocol tcp --port 8090 --cidr 0.0.0.0/0
fi
SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$SG_NAME" \
        --query 'SecurityGroups[0].GroupId' --output text)
aws ec2 create-tags --resources "$SG_ID" --tags Key=project,Value=oracle 2>/dev/null || true

# --- user data: docker + repo + compose up with S3 upload enabled -----------
USER_DATA=$(cat <<EOF
#!/bin/bash
dnf install -y docker git -q
systemctl enable --now docker
git clone --quiet "$REPO" /opt/cloud-oracle
cd /opt/cloud-oracle/workload
S3_BUCKET=$BUCKET docker compose up -d --build
EOF
)

AMI=$(aws ssm get-parameter \
    --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --region "$REGION" --query 'Parameter.Value' --output text)

INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI" --instance-type t3.micro --region "$REGION" \
    --key-name "$KEYPAIR" --security-group-ids "$SG_ID" \
    --iam-instance-profile Name="$PROFILE" \
    --user-data "$(base64 -w0 <<<"$USER_DATA")" \
    --count 1 \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=project,Value=oracle}]' \
                       'ResourceType=volume,Tags=[{Key=project,Value=oracle}]' \
    --query 'Instances[0].InstanceId' --output text)
echo "launched $INSTANCE_ID (t3.micro, $REGION); waiting for it to be running"

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
DNS=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
      --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "$INSTANCE_ID" > /tmp/oracle-instance-id
echo "$DNS"         > /tmp/oracle-instance-dns
echo
echo "docker build takes ~3-4 min after boot; stack ready around: $DNS:8090"
echo "NEXT (laptop, in repo root):"
echo "  workload/.venv/bin/locust -f workload/locust/locustfile.py -H http://$DNS:8090 --headless -t 10m"
echo "then: aws s3 ls s3://$BUCKET/   # collector uploads every 5 min"
echo "teardown: infra/aws-down.sh"
