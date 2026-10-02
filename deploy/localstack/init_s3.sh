#!/usr/bin/env bash
set -eo pipefail

echo "Initializing LocalStack S3 buckets for RiskGraph Platform..."

awslocal s3 mb s3://riskgraph-lake || true
awslocal s3api put-bucket-cors --bucket riskgraph-lake --cors-configuration '{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
      "AllowedOrigins": ["*"],
      "ExposeHeaders": ["ETag"]
    }
  ]
}' || true

echo "Created bucket s3://riskgraph-lake successfully."
