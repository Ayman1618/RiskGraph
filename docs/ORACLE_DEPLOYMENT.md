# RiskGraph — Oracle Cloud Always Free Production Deployment Guide

This guide provides step-by-step instructions to deploy the complete **RiskGraph** platform to **Oracle Cloud Infrastructure (OCI)** under the permanent **Always Free Tier** ($0/month).

---

## 1. Architecture & Security Model

```
                    INTERNET (Recruiters / Public)
                                  │
                                  ▼ [Ports 80 / 443 ONLY]
           ┌──────────────────────────────────────────────┐
           │        Nginx Edge Reverse Proxy (Host)       │
           │  • Static Single Page App (Frontend)         │
           │  • Routing /api/ -> api:8000                 │
           │  • Routing /health -> api:8000/health        │
           │  • Routing /docs -> api:8000/docs            │
           │  • Routing /grafana/ -> grafana:3000/        │
           └──────────────────────┬───────────────────────┘
                                  │ (Private Bridge Network: riskgraph-prod-net)
     ┌────────────────────────────┼────────────────────────────┐
     ▼                            ▼                            ▼
┌──────────────┐          ┌──────────────┐          ┌───────────────────────┐
│ FastAPI Core │          │ PySpark      │          │ Apache Airflow        │
│ (api:8000)   │          │ Streaming    │          │ Orchestrator          │
└──────┬───────┘          └──────┬───────┘          └───────────┬───────────┘
       │                         │                              │
       └──────────────┬──────────┴──────────────┬───────────────┘
                      ▼                         ▼
            ┌───────────────────┐     ┌───────────────────┐
            │ PostgreSQL (5432) │     │ Apache Kafka      │
            │ Relational Ledger │     │ + Zookeeper       │
            └───────────────────┘     └───────────────────┘
                      ▼                         ▼
            ┌───────────────────┐     ┌───────────────────┐
            │ Neo4j (7474/7687) │     │ Redis (6379)      │
            │ Identity Graph    │     │ Velocity Cache    │
            └───────────────────┘     └───────────────────┘
                      ▼                         ▼
            ┌───────────────────┐     ┌───────────────────┐
            │ LocalStack S3     │     │ Prometheus (9090) │
            │ Lakehouse Buckets │     │ & Grafana (3000)  │
            └───────────────────┘     └───────────────────┘
```

### Security Highlights
- **Only Ports 80 and 443 are publicly accessible.**
- All databases and infrastructure components (PostgreSQL, Neo4j, Redis, Kafka, Zookeeper, LocalStack S3, Airflow, Spark, Prometheus, Grafana) have **no host port bindings**. They communicate exclusively over the private Docker internal network `riskgraph-prod-net`.
- Hardcoded localhost endpoints have been replaced with relative paths for production and dynamic runtime environment indicators.

---

## 2. Oracle VM Requirements (Always Free)

Oracle Cloud provides an **Always Free Ampere A1 Compute** allowance of up to 4 OCPUs and 24 GB of RAM, which can be allocated to a single virtual machine:

| Parameter | Recommended Free Tier Specification |
| :--- | :--- |
| **Shape** | `VM.Standard.A1.Flex` (Ampere ARM64) |
| **OCPUs** | `4 OCPU` |
| **Memory** | `24 GB RAM` |
| **Operating System** | Canonical Ubuntu 22.04 / 24.04 LTS (AArch64) or Oracle Linux 8 / 9 |
| **Boot Volume** | `100 GB - 200 GB` (Free tier provides up to 200 GB total) |
| **Public IPv4** | Automatically assigned ephemeral or reserved public IP |
| **Total Monthly Cost**| **$0.00 / ₹0.00 (Permanent Always Free)** |

---

## 3. Required Oracle Cloud VCN & Ingress Rules

In your OCI Web Console:

1. Navigate to **Networking** → **Virtual Cloud Networks (VCN)**.
2. Select your VCN and click on **Security Lists** → **Default Security List for <your-vcn>**.
3. Under **Ingress Rules**, click **Add Ingress Rules** and configure:

| Source CIDR | IP Protocol | Source Port Range | Destination Port Range | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0.0.0.0/0` | `TCP` | `All` | `80` | Allow HTTP Web Traffic (Nginx) |
| `0.0.0.0/0` | `TCP` | `All` | `443` | Allow HTTPS Web Traffic (Nginx SSL) |
| `0.0.0.0/0` (or your IP) | `TCP` | `All` | `22` | Allow SSH Remote Access |

> [!CAUTION]
> Do **NOT** add ingress rules for ports `5432`, `7474`, `7687`, `6379`, `9092`, `2181`, `4566`, `8080`, `9090`, or `3000`. These must remain private inside Docker!

---

## 4. Step-by-Step Deployment Instructions

### Step 1: Connect to your Oracle VM via SSH
```bash
ssh -i /path/to/your/oci-private-key.key ubuntu@<YOUR_VM_PUBLIC_IP>
```
*(If using Oracle Linux, the default username is `opc` instead of `ubuntu`)*

---

### Step 2: Clone the RiskGraph Repository
```bash
git clone https://github.com/Ayman1618/RiskGraph.git
cd RiskGraph
```

---

### Step 3: Run the VM Setup Script
The automated setup script installs Docker, Docker Compose, sets kernel parameters for Neo4j/Kafka (`vm.max_map_count=262144`), and configures the host firewall:
```bash
sudo bash deploy/oracle/setup_vm.sh
```

Apply user group permissions (or log out and re-SSH):
```bash
newgrp docker
```

---

### Step 4: Configure Production Environment Variables
Copy the production template:
```bash
cp .env.production.example .env.production
```

Edit `.env.production` to set your VM's public IP or domain name and secure passwords:
```bash
nano .env.production
```
Make sure `PUBLIC_HOST` is set to your VM's public IP (e.g. `PUBLIC_HOST=129.146.xxx.xxx`).

---

### Step 5: Execute Production Deployment
Run the automated deployment script:
```bash
bash deploy/oracle/deploy.sh
```

This script will:
1. Pull all native ARM64 multi-arch images.
2. Build the API and Spark Streaming containers.
3. Launch all 12 services using `docker-compose.prod.yml`.
4. Wait for database and broker health checks to pass.
5. Seed initial demo transactions and baseline data quality metrics.

---

### Step 6: Verify Deployment with the Smoke Test Suite
Run the automated public verification suite:
```bash
bash deploy/oracle/smoke_test.sh http://localhost
```
Or test externally using your Public IP:
```bash
bash deploy/oracle/smoke_test.sh http://<YOUR_VM_PUBLIC_IP>
```

Expected output:
```
======================================================
 RiskGraph Production Public Verification Suite
 Target: http://129.146.xxx.xxx
======================================================

1. Edge Reverse Proxy & Routing:
  [PASS] Nginx Health Probe (HTTP 200)
  [PASS] Frontend Web App Root (HTTP 200)

2. Core Application API & Specs:
  [PASS] FastAPI Platform Health (HTTP 200)
  [PASS] OpenAPI Interactive Swagger Docs (HTTP 200)
  [PASS] OpenAPI JSON Specification (HTTP 200)

3. Fraud & Identity Engine API Endpoints:
  [PASS] Risk Rules Inventory (HTTP 200)
  [PASS] Risk Engine Real-Time Statistics (HTTP 200)
  [PASS] Recent Transactions Ledger (HTTP 200)
  [PASS] Graph Fraud Ring Detection (HTTP 200)
  [PASS] Data Quality Verification Reports (HTTP 200)
  [PASS] Data Pipeline Infrastructure Status (HTTP 200)

4. Real-Time Transaction Evaluation Pipeline:
  [PASS] POST /api/v1/transactions/evaluate (HTTP 200, Decision: APPROVE, Score: 0.0)

5. Observability & Telemetry:
  [PASS] Prometheus Metrics Scrape (HTTP 200)
  [PASS] Grafana Dashboard UI (HTTP 200)

======================================================
 Smoke Test Complete: ALL 13/13 CHECKS PASSED!
======================================================
```

---

## 5. Recruiter & Evaluator Access URLs

Once deployed, share these direct links with reviewers:

| Service | Public URL | Description |
| :--- | :--- | :--- |
| **RiskGraph Terminal** | `http://<YOUR_VM_PUBLIC_IP>/` | Complete financial intelligence & fraud operations frontend |
| **Interactive API Docs**| `http://<YOUR_VM_PUBLIC_IP>/docs` | Swagger UI for live REST API exploration |
| **Grafana Dashboards** | `http://<YOUR_VM_PUBLIC_IP>/grafana/` | Live observability metrics & pipeline telemetry |
| **System Health** | `http://<YOUR_VM_PUBLIC_IP>/health` | Comprehensive infrastructure & database health check |

---

## 6. Daily Management & Operational Commands

All production operations use `docker-compose.prod.yml`:

```bash
# Check status of all containers
docker compose --env-file .env.production -f docker-compose.prod.yml ps

# View live logs from all services
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f

# View logs for a specific service (e.g. API or Spark)
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f api
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f stream-processor

# Restart the production stack
docker compose --env-file .env.production -f docker-compose.prod.yml restart

# Stop the platform gracefully
docker compose --env-file .env.production -f docker-compose.prod.yml down

# Run interactive CLI commands inside the API container
docker exec -it riskgraph-api python cli.py status
docker exec -it riskgraph-api python cli.py evaluate-tx --amount 9200 --emulator
docker exec -it riskgraph-api python cli.py run-dq-suite
docker exec -it riskgraph-api python cli.py detect-rings
```

---

## 7. Troubleshooting

### Port 80 Not Reachable from External Browser
1. **Check OCI VCN Ingress Rules**: Ensure TCP port 80 is allowed from CIDR `0.0.0.0/0`.
2. **Check Host Firewall**: Oracle Cloud images have default `iptables` rules that reject inbound traffic. Verify by checking:
   ```bash
   sudo iptables -L INPUT -n --line-numbers | grep -E "80|443"
   ```
   If missing, run:
   ```bash
   sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
   ```

### Check Available Memory & Disk Space
```bash
free -h
df -h
docker stats --no-stream
```
*(Active baseline across all 12 services is ~7.5 GB RAM, safely within the 24 GB RAM limit of the Ampere A1 instance).*
