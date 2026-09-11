#!/bin/bash
set -euo pipefail

# ════════════════════════════════════════════════════════════════════
# F&O Trading Dashboard — Minimal Deployment Script
# ════════════════════════════════════════════════════════════════════
#
# Deploys the complete F&O analysis platform to any AWS account:
#   - S3 static website (frontend)
#   - API Gateway (REST)
#   - Lambda: market-data (NSE + Dhan data)
#   - Lambda: fno-agent (Bedrock Claude analysis)
#   - IAM role for Lambdas
#
# Prerequisites:
#   - AWS CLI configured with target account credentials
#   - Bedrock model access enabled (Claude Haiku 4.5)
#   - Dhan API credentials (client ID + access token)
#
# Usage:
#   ./deploy-minimal.sh [--region us-west-2] [--dhan-client-id ID] [--dhan-token TOKEN]
# ════════════════════════════════════════════════════════════════════

# ── Defaults ───────────────────────────────────────────────────────
REGION="us-west-2"
DHAN_CLIENT_ID=""
DHAN_ACCESS_TOKEN=""
BEDROCK_MODEL_ID="us.anthropic.claude-haiku-4-5-20251001-v1:0"
PREFIX="fno-trading"

# ── Parse args ─────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --region) REGION="$2"; shift 2 ;;
        --dhan-client-id) DHAN_CLIENT_ID="$2"; shift 2 ;;
        --dhan-token) DHAN_ACCESS_TOKEN="$2"; shift 2 ;;
        --model-id) BEDROCK_MODEL_ID="$2"; shift 2 ;;
        --prefix) PREFIX="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ── Prompt for missing Dhan creds ─────────────────────────────────
if [[ -z "$DHAN_CLIENT_ID" ]]; then
    read -p "Enter Dhan Client ID: " DHAN_CLIENT_ID
fi
if [[ -z "$DHAN_ACCESS_TOKEN" ]]; then
    read -sp "Enter Dhan Access Token: " DHAN_ACCESS_TOKEN
    echo
fi

# ── Derived names ──────────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_NAME="${PREFIX}-lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
MARKET_DATA_LAMBDA="${PREFIX}-market-data"
AGENT_LAMBDA="${PREFIX}-agent"
API_NAME="${PREFIX}-api"
BUCKET_NAME="${PREFIX}-frontend-${ACCOUNT_ID}"

echo "══════════════════════════════════════════════════"
echo "  F&O Trading Dashboard — Deployment"
echo "══════════════════════════════════════════════════"
echo "  Account:  ${ACCOUNT_ID}"
echo "  Region:   ${REGION}"
echo "  Prefix:   ${PREFIX}"
echo "  Model:    ${BEDROCK_MODEL_ID}"
echo "  Bucket:   ${BUCKET_NAME}"
echo "══════════════════════════════════════════════════"
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ════════════════════════════════════════════════════════════════════
# STEP 1: IAM Role
# ════════════════════════════════════════════════════════════════════
echo "▸ [1/7] Creating IAM role..."

TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

if aws iam get-role --role-name "$ROLE_NAME" --region "$REGION" &>/dev/null; then
    echo "  Role already exists: ${ROLE_NAME}"
else
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --region "$REGION" --output text --query 'Role.Arn'

    # Attach basic Lambda + Bedrock permissions
    aws iam attach-role-policy --role-name "$ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    aws iam attach-role-policy --role-name "$ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess

    echo "  Created role: ${ROLE_NAME}"
    echo "  Waiting 10s for IAM propagation..."
    sleep 10
fi

# ════════════════════════════════════════════════════════════════════
# STEP 2: Package Lambdas
# ════════════════════════════════════════════════════════════════════
echo "▸ [2/7] Packaging Lambda functions..."

MARKET_DATA_ZIP="/tmp/${MARKET_DATA_LAMBDA}.zip"
AGENT_ZIP="/tmp/${AGENT_LAMBDA}.zip"

cd "${PROJECT_DIR}/lambdas/market-data"
zip -j "$MARKET_DATA_ZIP" lambda_function.py
echo "  Packaged: market-data Lambda"

cd "${PROJECT_DIR}/lambdas/fno-agent"
zip -j "$AGENT_ZIP" lambda_function.py
echo "  Packaged: fno-agent Lambda"

# ════════════════════════════════════════════════════════════════════
# STEP 3: Deploy Lambdas
# ════════════════════════════════════════════════════════════════════
echo "▸ [3/7] Deploying Lambda functions..."

deploy_lambda() {
    local FUNC_NAME="$1"
    local ZIP_FILE="$2"
    local TIMEOUT="$3"
    local ENV_VARS="$4"

    if aws lambda get-function --function-name "$FUNC_NAME" --region "$REGION" &>/dev/null; then
        echo "  Updating: ${FUNC_NAME}"
        aws lambda update-function-code \
            --function-name "$FUNC_NAME" \
            --zip-file "fileb://${ZIP_FILE}" \
            --region "$REGION" --output text --query 'FunctionName'
        sleep 2
        aws lambda update-function-configuration \
            --function-name "$FUNC_NAME" \
            --timeout "$TIMEOUT" \
            --memory-size 256 \
            --environment "$ENV_VARS" \
            --region "$REGION" --output text --query 'FunctionName' 2>/dev/null || true
    else
        echo "  Creating: ${FUNC_NAME}"
        aws lambda create-function \
            --function-name "$FUNC_NAME" \
            --runtime python3.12 \
            --handler lambda_function.lambda_handler \
            --role "$ROLE_ARN" \
            --zip-file "fileb://${ZIP_FILE}" \
            --timeout "$TIMEOUT" \
            --memory-size 256 \
            --environment "$ENV_VARS" \
            --region "$REGION" --output text --query 'FunctionName'
    fi
}

deploy_lambda "$MARKET_DATA_LAMBDA" "$MARKET_DATA_ZIP" 30 \
    "Variables={DHAN_CLIENT_ID=${DHAN_CLIENT_ID},DHAN_ACCESS_TOKEN=${DHAN_ACCESS_TOKEN}}"

deploy_lambda "$AGENT_LAMBDA" "$AGENT_ZIP" 60 \
    "Variables={BEDROCK_MODEL_ID=${BEDROCK_MODEL_ID},REGION=${REGION}}"

echo "  Lambdas deployed."

# ════════════════════════════════════════════════════════════════════
# STEP 4: API Gateway
# ════════════════════════════════════════════════════════════════════
echo "▸ [4/7] Setting up API Gateway..."

# Check for existing API
API_ID=$(aws apigateway get-rest-apis --region "$REGION" \
    --query "items[?name=='${API_NAME}'].id" --output text)

if [[ -z "$API_ID" || "$API_ID" == "None" ]]; then
    API_ID=$(aws apigateway create-rest-api \
        --name "$API_NAME" \
        --description "F&O Trading Analysis API" \
        --endpoint-configuration types=REGIONAL \
        --region "$REGION" --output text --query 'id')
    echo "  Created API: ${API_ID}"
else
    echo "  Using existing API: ${API_ID}"
fi

ROOT_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --region "$REGION" \
    --query "items[?path=='/'].id" --output text)

# Helper: create resource + POST + OPTIONS
setup_route() {
    local RESOURCE_PATH="$1"
    local LAMBDA_NAME="$2"
    local LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${LAMBDA_NAME}"
    local INTEGRATION_URI="arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations"

    # Create resource (ignore if exists)
    local RESOURCE_ID
    RESOURCE_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --region "$REGION" \
        --query "items[?path=='/${RESOURCE_PATH}'].id" --output text)

    if [[ -z "$RESOURCE_ID" || "$RESOURCE_ID" == "None" ]]; then
        RESOURCE_ID=$(aws apigateway create-resource \
            --rest-api-id "$API_ID" \
            --parent-id "$ROOT_ID" \
            --path-part "$RESOURCE_PATH" \
            --region "$REGION" --output text --query 'id')
    fi

    # POST method
    aws apigateway put-method \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method POST \
        --authorization-type NONE \
        --region "$REGION" --output text 2>/dev/null || true

    aws apigateway put-integration \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method POST \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "$INTEGRATION_URI" \
        --region "$REGION" --output text

    # OPTIONS for CORS
    aws apigateway put-method \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method OPTIONS \
        --authorization-type NONE \
        --region "$REGION" --output text 2>/dev/null || true

    aws apigateway put-integration \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method OPTIONS \
        --type MOCK \
        --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
        --region "$REGION" --output text

    aws apigateway put-method-response \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method OPTIONS \
        --status-code 200 \
        --response-parameters '{"method.response.header.Access-Control-Allow-Headers":false,"method.response.header.Access-Control-Allow-Methods":false,"method.response.header.Access-Control-Allow-Origin":false}' \
        --response-models '{"application/json": "Empty"}' \
        --region "$REGION" --output text 2>/dev/null || true

    aws apigateway put-integration-response \
        --rest-api-id "$API_ID" \
        --resource-id "$RESOURCE_ID" \
        --http-method OPTIONS \
        --status-code 200 \
        --response-parameters "{\"method.response.header.Access-Control-Allow-Headers\":\"'Content-Type,Authorization'\",\"method.response.header.Access-Control-Allow-Methods\":\"'POST,OPTIONS'\",\"method.response.header.Access-Control-Allow-Origin\":\"'*'\"}" \
        --region "$REGION" --output text 2>/dev/null || true

    # Lambda permission
    aws lambda add-permission \
        --function-name "$LAMBDA_NAME" \
        --statement-id "apigw-${RESOURCE_PATH}" \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT_ID}:${API_ID}/*/POST/${RESOURCE_PATH}" \
        --region "$REGION" --output text 2>/dev/null || true

    echo "  Route: /${RESOURCE_PATH} -> ${LAMBDA_NAME}"
}

setup_route "market-data" "$MARKET_DATA_LAMBDA"
setup_route "agent" "$AGENT_LAMBDA"

# Deploy API
aws apigateway create-deployment \
    --rest-api-id "$API_ID" \
    --stage-name prod \
    --region "$REGION" --output text --query 'id'

API_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod"
echo "  API deployed: ${API_URL}"

# ════════════════════════════════════════════════════════════════════
# STEP 5: S3 Frontend Bucket
# ════════════════════════════════════════════════════════════════════
echo "▸ [5/7] Setting up S3 frontend..."

if aws s3api head-bucket --bucket "$BUCKET_NAME" --region "$REGION" 2>/dev/null; then
    echo "  Bucket exists: ${BUCKET_NAME}"
else
    aws s3api create-bucket \
        --bucket "$BUCKET_NAME" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION" \
        --output text 2>/dev/null

    aws s3api put-public-access-block \
        --bucket "$BUCKET_NAME" \
        --public-access-block-configuration \
            BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false \
        --region "$REGION"

    aws s3api put-bucket-policy \
        --bucket "$BUCKET_NAME" \
        --policy "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Sid\": \"PublicRead\",
                \"Effect\": \"Allow\",
                \"Principal\": \"*\",
                \"Action\": \"s3:GetObject\",
                \"Resource\": \"arn:aws:s3:::${BUCKET_NAME}/*\"
            }]
        }"

    aws s3 website "s3://${BUCKET_NAME}" \
        --index-document index.html \
        --error-document index.html
    echo "  Created bucket: ${BUCKET_NAME}"
fi

# ════════════════════════════════════════════════════════════════════
# STEP 6: Generate config & upload frontend
# ════════════════════════════════════════════════════════════════════
echo "▸ [6/7] Uploading frontend..."

FRONTEND_DIR="${PROJECT_DIR}/frontend"

# Generate config.js with correct API URL
cat > /tmp/config.template.js <<JSEOF
const CONFIG = (function() {
    return {
        REST_API_URL: '${API_URL}',
        WEBSOCKET_URL: '',
        REGION: '${REGION}',
        AUTH_API_URL: '',
        APP_NAME: 'WealthAI F&O Dashboard',
        VERSION: '2.0.0',
    };
})();
JSEOF

aws s3 cp /tmp/config.template.js "s3://${BUCKET_NAME}/config.template.js" \
    --content-type "application/javascript" --region "$REGION"

# Upload HTML files
for f in trading-dashboard.html index.html client-dashboard.html observability.html \
         performance-tuning.html loadtest.html; do
    if [[ -f "${FRONTEND_DIR}/${f}" ]]; then
        aws s3 cp "${FRONTEND_DIR}/${f}" "s3://${BUCKET_NAME}/${f}" \
            --content-type "text/html" --region "$REGION"
        echo "  Uploaded: ${f}"
    fi
done

# Upload CSS/JS/assets
for f in styles.css favicon.svg; do
    if [[ -f "${FRONTEND_DIR}/${f}" ]]; then
        local_ct="text/css"
        [[ "$f" == *.svg ]] && local_ct="image/svg+xml"
        [[ "$f" == *.js ]] && local_ct="application/javascript"
        aws s3 cp "${FRONTEND_DIR}/${f}" "s3://${BUCKET_NAME}/${f}" \
            --content-type "$local_ct" --region "$REGION"
        echo "  Uploaded: ${f}"
    fi
done

SITE_URL="http://${BUCKET_NAME}.s3-website-${REGION}.amazonaws.com"

# ════════════════════════════════════════════════════════════════════
# STEP 7: Verify
# ════════════════════════════════════════════════════════════════════
echo "▸ [7/7] Verifying deployment..."
echo

# Quick smoke test
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_URL}/market-data" \
    -H 'Content-Type: application/json' \
    -d '{"action":"indices"}' || echo "000")

if [[ "$RESPONSE" == "200" ]]; then
    echo "  ✓ Market data API responding"
else
    echo "  ⚠ Market data API returned HTTP ${RESPONSE} (may need a moment)"
fi

echo
echo "══════════════════════════════════════════════════════════════"
echo "  DEPLOYMENT COMPLETE"
echo "══════════════════════════════════════════════════════════════"
echo
echo "  Dashboard:  ${SITE_URL}/trading-dashboard.html"
echo "  API:        ${API_URL}"
echo "  Lambdas:    ${MARKET_DATA_LAMBDA}, ${AGENT_LAMBDA}"
echo "  S3 Bucket:  ${BUCKET_NAME}"
echo "  Region:     ${REGION}"
echo
echo "  Next steps:"
echo "    1. Enable Bedrock model access: ${BEDROCK_MODEL_ID}"
echo "       Console: https://${REGION}.console.aws.amazon.com/bedrock/home?region=${REGION}#/modelaccess"
echo "    2. Open dashboard: ${SITE_URL}/trading-dashboard.html"
echo "    3. Click 'Analyze' to get AI recommendations"
echo
echo "  Monthly cost estimate: ~\$1-3 (Lambda free tier + Bedrock pay-per-use)"
echo "══════════════════════════════════════════════════════════════"
