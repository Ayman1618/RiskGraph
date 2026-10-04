#!/usr/bin/env bash
# ==============================================================================
# RiskGraph Platform — Oracle Cloud Production Deployment Script
# Target: Oracle Cloud Always Free Ampere A1 (ARM64)
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"

log_info "=================================================="
log_info "RiskGraph — Production Deployment Initiation"
log_info "Working directory: $REPO_ROOT"
log_info "Compose configuration: $COMPOSE_FILE"
log_info "=================================================="

# 1. Check prerequisites
if ! command -v docker &> /dev/null; then
  log_error "Docker is not installed! Please run 'sudo bash deploy/oracle/setup_vm.sh' first."
  exit 1
fi

if ! docker compose version &> /dev/null; then
  log_error "Docker Compose plugin is not installed!"
  exit 1
fi

# 2. Check environment configuration
if [ ! -f "$ENV_FILE" ]; then
  if [ -f ".env.production.example" ]; then
    log_warn "No .env.production file found. Generating one from .env.production.example..."
    cp .env.production.example .env.production
    # Attempt to detect public IP
    DETECTED_IP=$(curl -s -m 3 https://ifconfig.me 2>/dev/null || curl -s -m 3 https://api.ipify.org 2>/dev/null || echo "localhost")
    sed -i.bak "s/your-vm-public-ip-or-domain/$DETECTED_IP/g" .env.production && rm -f .env.production.bak
    log_success "Created .env.production with detected host: $DETECTED_IP"
  else
    log_error "Missing both .env.production and .env.production.example!"
    exit 1
  fi
fi

# 3. Pull third-party images and build platform images
log_info "Pulling official base container images..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull --ignore-buildable || true

log_info "Building application containers (FastAPI, Spark Streaming)..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --parallel

# 4. Start production stack
log_info "Starting RiskGraph production services in background..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans

# 5. Wait for core databases to become healthy
log_info "Awaiting service health convergence..."
MAX_ATTEMPTS=30
ATTEMPT=1
SERVICES_READY=false

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
  PG_STATUS=$(docker inspect --format='{{json .State.Health.Status}}' riskgraph-postgres 2>/dev/null || echo '"unknown"')
  REDIS_STATUS=$(docker inspect --format='{{json .State.Health.Status}}' riskgraph-redis 2>/dev/null || echo '"unknown"')
  NEO_STATUS=$(docker inspect --format='{{json .State.Health.Status}}' riskgraph-neo4j 2>/dev/null || echo '"unknown"')
  API_STATUS=$(docker inspect --format='{{json .State.Health.Status}}' riskgraph-api 2>/dev/null || echo '"unknown"')

  if [ "$PG_STATUS" = '"healthy"' ] && [ "$REDIS_STATUS" = '"healthy"' ] && [ "$NEO_STATUS" = '"healthy"' ] && [ "$API_STATUS" = '"healthy"' ]; then
    SERVICES_READY=true
    break
  fi

  echo -n "."
  sleep 4
  ATTEMPT=$((ATTEMPT + 1))
done
echo ""

if [ "$SERVICES_READY" = false ]; then
  log_warn "Some services are still initializing. Reviewing container status:"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
else
  log_success "Core platform services are HEALTHY!"
fi

# 6. Seed demo telemetry & run initial data quality checks
log_info "Initializing sample risk evaluation and data quality baseline..."
docker exec riskgraph-api python -c "
import sys
from src.generator.generator import SyntheticEventGenerator
from src.data_quality.dq_runner import DataQualityRunner
import pandas as pd
print('Generating initial dataset sample...')
gen = SyntheticEventGenerator(fraud_ratio=0.25)
events = [tx.model_dump() for tx, _ in gen.generate_stream(rate_per_sec=0, max_events=200)]
df = pd.DataFrame(events)
runner = DataQualityRunner()
report = runner.run_suite(df, dataset_name='initial_bootstrap')
print(f'Initial Data Quality check completed: {report.passed_checks}/{report.total_checks} checks passed.')
" || log_warn "Bootstrap data generation skipped or partially succeeded."

# 7. Print access summary
PUBLIC_HOST=$(grep "^PUBLIC_HOST=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- || echo "localhost")
if [ -z "$PUBLIC_HOST" ] || [ "$PUBLIC_HOST" = "your-vm-public-ip-or-domain" ]; then
  PUBLIC_HOST=$(curl -s -m 3 https://ifconfig.me 2>/dev/null || echo "localhost")
fi

log_success "=================================================="
log_success "RiskGraph Production Stack Deployed Successfully!"
log_success "=================================================="
echo -e "Web Application (Frontend):  ${GREEN}http://${PUBLIC_HOST}/${NC}"
echo -e "Interactive Swagger API Docs:${GREEN}http://${PUBLIC_HOST}/docs${NC}"
echo -e "Health Check Endpoint:       ${GREEN}http://${PUBLIC_HOST}/health${NC}"
echo -e "Grafana Dashboards:          ${GREEN}http://${PUBLIC_HOST}/grafana/${NC}"
echo -e "System Metrics:              ${GREEN}http://${PUBLIC_HOST}/api/v1/metrics${NC}"
echo ""
echo -e "${YELLOW}To execute comprehensive verification tests, run:${NC}"
echo "  bash deploy/oracle/smoke_test.sh http://${PUBLIC_HOST}"
