# 🏛️ RiskGraph Architecture & Engineering Deep-Dive

## 1. Design Principles

1. **Stream-Batch Duality**: Structured Streaming handles near real-time ingestion, watermarking, and operational store population, while PySpark Batch handles heavy deduplication, complex identity feature marts, and lakehouse curation.
2. **Graph-Enhanced Identity Resolution**: Relational databases struggle with recursive N-hop graph traversals. By extracting Gold layer graph nodes and edges into **Neo4j**, RiskGraph evaluates identity rings and mule account chains in sub-10ms queries.
3. **Decoupled Low-Latency Serving**: The real-time evaluation API utilizes **Redis** for sub-millisecond rolling window token buckets and in-memory caches, offloading transactional load while remaining resilient to database spikes.
4. **Data Quality as a First-Class Citizen**: Automated quality checks act as circuit-breaker gates between Bronze, Silver, and Gold transitions to prevent bad data from polluting downstream feature stores and graph databases.

---

## 2. Medallion Lakehouse Layers

### 🥉 Bronze Layer (`s3a://riskgraph-lake/bronze/`)
- **Format**: Parquet / Delta.
- **Partitioning**: Year / Month / Day (`year=YYYY/month=MM/day=DD`).
- **Nature**: Append-only raw event archive directly ingested from Kafka.
- **Retention**: Immutable historical raw events.

### 🥈 Silver Layer (`s3a://riskgraph-lake/silver/`)
- **Format**: Parquet.
- **Partitioning**: Transaction Date (`tx_date=YYYY-MM-DD`).
- **Transformations**:
  - Null validation on primary keys (`transaction_id`, `user_id`).
  - Deduplication via `row_number() OVER (PARTITION BY transaction_id ORDER BY timestamp DESC)`.
  - Type casting & standardizations (currency uppercase, amounts positive float, whitespace trimming).
  - Derived attributes: `ip_network_prefix`, `is_high_value`.

### 🥇 Gold Layer (`s3a://riskgraph-lake/gold/`)
- **Format**: Parquet marts.
- **Datasets**:
  1. `features_user_daily`: Daily transaction volume, average spend, distinct devices count, distinct IPs, distinct cards.
  2. `features_device_risk`: Distinct user count per device hardware fingerprint, multi-user sharing flags.
  3. `graph_nodes`: Unified node extract (`User`, `Device`, `IP`, `Card`, `Merchant`).
  4. `graph_edges`: Unified edge extract (`USES_DEVICE`, `ORIGINATED_FROM_IP`, `PAID_WITH`, `TRANSACTED_WITH`).

---

## 3. Neo4j Graph Model & Identity Ring Detection

### Graph Schema
- **Nodes**:
  - `(:User {id, kyc_status, risk_tier, is_fraudulent})`
  - `(:Device {id, fingerprint, is_emulator})`
  - `(:IP {id, subnet})`
  - `(:Card {id, bin_range})`
  - `(:Merchant {id, category})`
- **Edges**:
  - `(:User)-[:USES_DEVICE]->(:Device)`
  - `(:User)-[:ORIGINATED_FROM_IP]->(:IP)`
  - `(:User)-[:PAID_WITH]->(:Card)`
  - `(:User)-[:TRANSACTED_WITH]->(:Merchant)`

### Cypher Identity Ring Query
```cypher
MATCH (d:Device)<-[:USES_DEVICE]-(u:User)
WITH d, collect(u.id) AS users, count(u) AS user_count
WHERE user_count >= 3
RETURN d.id AS shared_device_id, users AS ring_members, user_count AS ring_size
ORDER BY ring_size DESC;
```

---

## 4. Real-Time Risk Decisioning Pipeline

1. **Request Ingestion**: Transaction parameters passed to `POST /api/v1/transactions/evaluate`.
2. **Sub-ms Velocity Lookup**: Redis queries sliding window sorted sets (`ZREMRANGEBYSCORE` + `ZCARD`).
3. **Blacklist Check**: Instant set check against known fraudulent IPs, devices, and cards.
4. **Graph Signal Fetch**: Real-time Cypher traversal queries shortest-path proximity to known fraud nodes and multi-user device sharing.
5. **Rule Scoring & Verdict**:
   - `Risk Score >= 80` OR Critical Amount OR Blacklist Hit OR Confirmed Ring => **`BLOCK`**
   - `Risk Score >= 35` OR High Velocity OR High Amount => **`REVIEW`**
   - Otherwise => **`APPROVE`**
6. **Telemetry & Audit**: Latency, triggered rule IDs, and decision counters published to Prometheus.
