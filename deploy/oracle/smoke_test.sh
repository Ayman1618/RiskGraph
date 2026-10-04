#!/usr/bin/env bash
# ==============================================================================
# RiskGraph Platform — Production Smoke Test & Verification Suite
#
# Usage:
#   bash deploy/oracle/smoke_test.sh [TARGET_URL]
#   Example:
#     bash deploy/oracle/smoke_test.sh http://129.146.xxx.xxx
#     bash deploy/oracle/smoke_test.sh http://localhost
# ==============================================================================

set -uo pipefail

TARGET_URL="${1:-http://localhost}"
# Strip trailing slash if present
TARGET_URL="${TARGET_URL%/}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

run_check() {
  local name="$1"
  local url="$2"
  local expected_status="$3"
  local extra_curl_args="${4:-}"

  TOTAL_TESTS=$((TOTAL_TESTS + 1))
  echo -ne "  [..] ${name} (${url}) ... "

  local http_code
  http_code=$(curl -s -o /tmp/smoke_resp.txt -w "%{http_code}" --max-time 10 $extra_curl_args "$url" || echo "000")

  if [ "$http_code" = "$expected_status" ]; then
    echo -e "\r  ${GREEN}[PASS]${NC} ${name} (HTTP ${http_code})"
    PASSED_TESTS=$((PASSED_TESTS + 1))
  else
    echo -e "\r  ${RED}[FAIL]${NC} ${name} (Expected HTTP ${expected_status}, got ${http_code})"
    if [ -f /tmp/smoke_resp.txt ] && [ -s /tmp/smoke_resp.txt ]; then
      echo -e "       ${YELLOW}Response excerpt:${NC} $(head -c 120 /tmp/smoke_resp.txt)..."
    fi
    FAILED_TESTS=$((FAILED_TESTS + 1))
  fi
}

echo -e "\n${BOLD}${CYAN}======================================================${NC}"
echo -e "${BOLD}${CYAN} RiskGraph Production Public Verification Suite${NC}"
echo -e "${BOLD}${CYAN} Target: ${TARGET_URL}${NC}"
echo -e "${BOLD}${CYAN}======================================================${NC}\n"

# 1. Edge & Proxy
echo -e "${BOLD}1. Edge Reverse Proxy & Routing:${NC}"
run_check "Nginx Health Probe" "$TARGET_URL/nginx-health" "200"
run_check "Frontend Web App Root" "$TARGET_URL/" "200"

# 2. FastAPI Core & Documentation
echo -e "\n${BOLD}2. Core Application API & Specs:${NC}"
run_check "FastAPI Platform Health" "$TARGET_URL/health" "200"
run_check "OpenAPI Interactive Swagger Docs" "$TARGET_URL/docs" "200"
run_check "OpenAPI JSON Specification" "$TARGET_URL/openapi.json" "200"

# 3. Fraud Engine & Analytics Endpoints
echo -e "\n${BOLD}3. Fraud & Identity Engine API Endpoints:${NC}"
run_check "Risk Rules Inventory" "$TARGET_URL/api/v1/rules" "200"
run_check "Risk Engine Real-Time Statistics" "$TARGET_URL/api/v1/risk/stats" "200"
run_check "Recent Transactions Ledger" "$TARGET_URL/api/v1/transactions?limit=5" "200"
run_check "Graph Fraud Ring Detection" "$TARGET_URL/api/v1/entities/rings" "200"
run_check "Data Quality Verification Reports" "$TARGET_URL/api/v1/dq/results" "200"
run_check "Data Pipeline Infrastructure Status" "$TARGET_URL/api/v1/pipeline/status" "200"

# 4. Live Risk Evaluation (POST)
echo -e "\n${BOLD}4. Real-Time Transaction Evaluation Pipeline:${NC}"
TOTAL_TESTS=$((TOTAL_TESTS + 1))
echo -ne "  [..] POST /api/v1/transactions/evaluate ... "
POST_PAYLOAD='{"user_id":"usr_test_verification_01","amount":7500.0,"ip_address":"198.51.100.22","device_id":"dev_test_smoke_01","is_emulator":false}'
POST_CODE=$(curl -s -o /tmp/smoke_post.txt -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -d "$POST_PAYLOAD" \
  --max-time 10 \
  "$TARGET_URL/api/v1/transactions/evaluate" || echo "000")

if [ "$POST_CODE" = "200" ]; then
  DECISION=$(grep -o '"decision":"[^"]*' /tmp/smoke_post.txt | cut -d':' -f2 | tr -d '"' || echo "UNKNOWN")
  SCORE=$(grep -o '"risk_score":[^,}]*' /tmp/smoke_post.txt | cut -d':' -f2 || echo "N/A")
  echo -e "\r  ${GREEN}[PASS]${NC} POST /api/v1/transactions/evaluate (HTTP 200, Decision: ${DECISION}, Score: ${SCORE})"
  PASSED_TESTS=$((PASSED_TESTS + 1))
else
  echo -e "\r  ${RED}[FAIL]${NC} POST /api/v1/transactions/evaluate (Expected HTTP 200, got ${POST_CODE})"
  FAILED_TESTS=$((FAILED_TESTS + 1))
fi

# 5. Observability
echo -e "\n${BOLD}5. Observability & Telemetry:${NC}"
run_check "Prometheus Metrics Scrape" "$TARGET_URL/api/v1/metrics" "200"
run_check "Grafana Dashboard UI" "$TARGET_URL/grafana/" "200"

# Summary
rm -f /tmp/smoke_resp.txt /tmp/smoke_post.txt
echo -e "\n${BOLD}======================================================${NC}"
if [ $FAILED_TESTS -eq 0 ]; then
  echo -e "${BOLD}${GREEN} Smoke Test Complete: ALL ${PASSED_TESTS}/${TOTAL_TESTS} CHECKS PASSED!${NC}"
  echo -e "${BOLD}======================================================${NC}\n"
  exit 0
else
  echo -e "${BOLD}${RED} Smoke Test Complete: ${FAILED_TESTS}/${TOTAL_TESTS} CHECKS FAILED!${NC}"
  echo -e "${BOLD}======================================================${NC}\n"
  exit 1
fi
