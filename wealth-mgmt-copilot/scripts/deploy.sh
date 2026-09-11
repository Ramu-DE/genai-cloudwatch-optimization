#!/bin/bash
set -euo pipefail

# WealthAI Copilot - Deployment Script
# Usage: ./deploy.sh [region] [environment]

REGION="${1:-us-west-2}"
ENV="${2:-prod}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
PROJECT="wealth-mgmt-copilot"
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================="
echo "  WealthAI Copilot Deployment"
echo "  Region: $REGION | Env: $ENV"
echo "  Account: $ACCOUNT_ID"
echo "============================================="

# Step 1: Create DynamoDB tables
echo ""
echo "[1/7] Creating DynamoDB tables..."
cd "$BASE_DIR"
python3 dynamodb/create_tables.py

# Step 2: Seed sample data
echo ""
echo "[2/7] Seeding sample data..."
python3 dynamodb/seed_data.py

# Step 3: Build and push agent Docker images to ECR
echo ""
echo "[3/7] Building agent Docker images..."

AGENTS=("market-analyst:market_analyst" "financial-planner:financial_planner" "tax-optimizer:tax_optimizer")

for agent_entry in "${AGENTS[@]}"; do
    IFS=':' read -r agent_dir agent_module <<< "$agent_entry"
    REPO_NAME="wealth-mgmt-${agent_dir}"

    echo "  Building $agent_dir..."

    # Create ECR repo if needed
    aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" 2>/dev/null || \
        aws ecr create-repository --repository-name "$REPO_NAME" --region "$REGION"

    # Login to ECR
    aws ecr get-login-password --region "$REGION" | \
        docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

    # Build and push
    cd "$BASE_DIR/agents/$agent_dir"
    docker build --platform linux/arm64 -t "$REPO_NAME:latest" .
    docker tag "$REPO_NAME:latest" "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}:latest"
    docker push "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}:latest"

    echo "  -> $agent_dir pushed to ECR"
done

# Step 4: Build and push Compliance Checker (Fargate)
echo ""
echo "[4/7] Building Compliance Checker (Fargate)..."
COMPLIANCE_REPO="wealth-mgmt-compliance-checker"

aws ecr describe-repositories --repository-names "$COMPLIANCE_REPO" --region "$REGION" 2>/dev/null || \
    aws ecr create-repository --repository-name "$COMPLIANCE_REPO" --region "$REGION"

cd "$BASE_DIR/agents/compliance-checker"
docker build --platform linux/arm64 -t "$COMPLIANCE_REPO:latest" .
docker tag "$COMPLIANCE_REPO:latest" "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${COMPLIANCE_REPO}:latest"
docker push "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${COMPLIANCE_REPO}:latest"
echo "  -> Compliance Checker pushed to ECR"

# Step 5: Package and deploy Lambda functions
echo ""
echo "[5/7] Deploying Lambda functions..."

LAMBDAS=("agent-router:wealth_mgmt_agent_router_lambda" "auth:wealth_mgmt_auth_lambda" "websocket:wealth_mgmt_websocket_lambda")

for lambda_entry in "${LAMBDAS[@]}"; do
    IFS=':' read -r lambda_dir lambda_name <<< "$lambda_entry"

    echo "  Packaging $lambda_name..."
    cd "$BASE_DIR/lambdas/$lambda_dir"
    zip -qr "/tmp/${lambda_name}.zip" *.py

    # Check if function exists
    if aws lambda get-function --function-name "$lambda_name" --region "$REGION" 2>/dev/null; then
        aws lambda update-function-code \
            --function-name "$lambda_name" \
            --zip-file "fileb:///tmp/${lambda_name}.zip" \
            --region "$REGION" > /dev/null
        echo "  -> Updated $lambda_name"
    else
        echo "  -> $lambda_name does not exist yet — deploy via CloudFormation first"
    fi
done

# Step 6: Deploy frontend to S3
echo ""
echo "[6/7] Deploying frontend..."
FRONTEND_BUCKET="wealth-mgmt-frontend-${ACCOUNT_ID}"

# Create config.js from template
cd "$BASE_DIR/frontend"
if [ -f config.template.js ]; then
    REST_API_URL=$(aws apigateway get-rest-apis --query "items[?name=='wealth_mgmt_api'].id" --output text --region "$REGION" 2>/dev/null || echo "PLACEHOLDER")
    WS_API_URL=$(aws apigatewayv2 get-apis --query "Items[?Name=='wealth_mgmt_websocket_api'].ApiId" --output text --region "$REGION" 2>/dev/null || echo "PLACEHOLDER")

    sed "s|REPLACE_REST_API_URL|https://${REST_API_URL}.execute-api.${REGION}.amazonaws.com/prod|g; \
         s|REPLACE_WEBSOCKET_URL|wss://${WS_API_URL}.execute-api.${REGION}.amazonaws.com/prod|g; \
         s|REPLACE_REGION|${REGION}|g" \
        config.template.js > config.js
fi

aws s3 sync "$BASE_DIR/frontend/" "s3://${FRONTEND_BUCKET}/" \
    --exclude "config.template.js" \
    --region "$REGION" 2>/dev/null || echo "  Frontend bucket not yet created — deploy CloudFormation first"

# Step 7: Deploy CloudWatch dashboard
echo ""
echo "[7/7] Deploying CloudWatch dashboard..."
cd "$BASE_DIR"
DASHBOARD_BODY=$(python3 -c "import json; d=json.load(open('cloudwatch/dashboard.json')); print(json.dumps(json.dumps(d['dashboardBody'])))")
aws cloudwatch put-dashboard \
    --dashboard-name "wealth_mgmt_copilot_dashboard" \
    --dashboard-body "$DASHBOARD_BODY" \
    --region "$REGION" 2>/dev/null || echo "  Dashboard deployment skipped (check permissions)"

echo ""
echo "============================================="
echo "  Deployment Complete!"
echo "============================================="
echo ""
echo "  Frontend: https://${FRONTEND_BUCKET}.s3-website-${REGION}.amazonaws.com"
echo "  Dashboard: https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=wealth_mgmt_copilot_dashboard"
echo ""
echo "  Demo credentials:"
echo "    Email: sarah.chen@email.com"
echo "    Password: demo123"
echo ""
