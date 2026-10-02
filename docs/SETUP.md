# 🛠️ RiskGraph Local Setup & Operational Guide

This guide walks you through launching and verifying the RiskGraph platform locally.

---

## 1. System Requirements

- **Docker Desktop** or Colima (configured with 4GB+ RAM allocated).
- **Python 3.10+**.
- **Docker Compose v2+**.

---

## 2. Environment Configuration

Copy the example environment file:
```bash
cp .env.example .env
```

All default values in `.env.example` work out of the box with the provided `docker-compose.yml`.

---

## 3. Launching the Infrastructure

Start all platform services:
```bash
make up
```

This starts:
- **Zookeeper & Kafka**: Port `9092` / `2181`
- **PostgreSQL 16**: Port `5432` (Auto-runs schema migrations)
- **Neo4j 5.20**: Port `7474` (HTTP) / `7687` (Bolt)
- **Redis 7.2**: Port `6379`
- **LocalStack (S3)**: Port `4566` (Auto-creates `riskgraph-lake` bucket)
- **FastAPI Decision Engine**: Port `8000`
- **Prometheus**: Port `9090`
- **Grafana**: Port `3000`

---

## 4. Verifying Services

Check the health of all platform components:
```bash
python cli.py status
```

Or hit the API health check:
```bash
curl http://localhost:8000/health
```

---

## 5. End-to-End Simulation Walkthrough

### Step 1: Generate Real-Time Event Stream
Generate a stream of 100 transactions with a 25% fraud injection ratio:
```bash
python cli.py generate-stream --rate 5 --count 100 --fraud-ratio 0.25
```

### Step 2: Test Real-Time Risk Engine
Evaluate a high-risk emulator transaction:
```bash
python cli.py evaluate-tx --amount 8500 --emulator
```

### Step 3: Run Data Quality Suite
Validate data quality across datasets:
```bash
python cli.py run-dq-suite --sample-size 500
```

### Step 4: Discover Graph Fraud Rings
Query Neo4j for multi-user device collision clusters:
```bash
python cli.py detect-rings --min-size 3
```

---

## 6. Accessing Observability Dashboards

- **Grafana**: Open [http://localhost:3000](http://localhost:3000) (Login: `admin` / `admin`).
  - Navigate to **Dashboards** > **RiskGraph Platform** > **RiskGraph — Fraud & Identity Operations**.
- **Neo4j Browser**: Open [http://localhost:7474](http://localhost:7474) (Login: `neo4j` / `riskgraph_graph_pass`).
- **FastAPI Swagger Docs**: Open [http://localhost:8000/docs](http://localhost:8000/docs).
