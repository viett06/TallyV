#!/bin/sh
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing "local/$S3_BUCKET" >/dev/null
mc anonymous set none "local/$S3_BUCKET" >/dev/null
mc admin user add local "$S3_ACCESS_KEY_ID" "$S3_SECRET_ACCESS_KEY" >/dev/null
cat > /tmp/tallyv-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:GetBucketLocation"], "Resource": ["arn:aws:s3:::$S3_BUCKET"]},
    {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": ["arn:aws:s3:::$S3_BUCKET"],
     "Condition": {"StringLike": {"s3:prefix": ["${S3_PREFIX}*"]}}},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
     "Resource": ["arn:aws:s3:::$S3_BUCKET/${S3_PREFIX}*"]}
  ]
}
EOF
mc admin policy create local tallyv-files /tmp/tallyv-policy.json >/dev/null
mc admin policy attach local tallyv-files --user "$S3_ACCESS_KEY_ID" >/dev/null
echo "Private bucket and scoped TallyV storage account ready."
