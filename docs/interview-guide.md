# 🎯 RiskGraph Interview Preparation Guide & Technical Deep-Dive

This guide prepares you to discuss the architecture, engineering trade-offs, and technical implementation of **RiskGraph** during Data Engineer interviews at Bureau and top-tier fintech / identity intelligence organizations.

---

## 1. Architecture & Design Principles

### Q: Walk me through the end-to-end architecture of RiskGraph.
**A**:
"RiskGraph is architected around a dual streaming-and-batch medallion lakehouse combined with an identity graph:
1. **Ingestion**: Raw transaction and identity events are generated and published to Apache Kafka (`fraud.transactions.raw`, `fraud.identity.raw`).
2. **Streaming Dual-Sink**: PySpark Structured Streaming consumes from Kafka, applies schema enforcement and event-time watermarking, and writes simultaneously to:
   - **S3 Bronze Layer** (LocalStack/Parquet) for immutable raw archiving.
   - **PostgreSQL ODS** for operational queries and real-time transaction lookups.
3. **Medallion Lakehouse Batch ETL**: PySpark batch jobs run daily to clean Bronze into **Silver** (deduplication, normalization, IP prefixing) and aggregate Silver into **Gold** feature marts (`features_user_daily`, `features_device_risk`, and graph node/edge extracts).
4. **Identity Graph**: Gold graph nodes and edges are loaded into **Neo4j** via parameterized Cypher `UNWIND` batches. Cypher analytics extract graph topology signals (e.g., shared device counts, multi-hop shortest paths to confirmed fraud nodes).
5. **Real-Time Risk Decisioning**: A **FastAPI** service integrates sub-millisecond sliding-window velocity from **Redis** (sorted sets), graph features from Neo4j, and rule weights to return synchronous `APPROVE`, `REVIEW`, or `BLOCK` verdicts with explainability.
6. **Orchestration & Observability**: Apache Airflow manages batch pipelines and quality gates; Prometheus and Grafana track real-time throughput, decision breakdown, and P95/P99 latency."

---

### Q: Why use both Kafka and PySpark instead of writing directly from the API to PostgreSQL?
**A**:
"Writing directly from a high-throughput API to a relational database creates tight coupling and database connection bottlenecks during traffic spikes. Kafka provides:
- **Decoupling & Backpressure**: Absorbs unpredictable transaction volume surges without dropping events.
- **Multi-Consumer Fan-Out**: The same raw stream feeds PySpark for lakehouse archiving, PostgreSQL for operational querying, and real-time fraud alert subscribers without duplicate ingestion pipelines.
- **Replayability**: If a downstream processor fails or schema logic changes, Kafka allows rewinding consumer offsets to reprocess historical events."

---

### Q: Why do you need Neo4j if you already have PostgreSQL?
**A**:
"Relational databases excel at structured ACID transactions and aggregate queries on tabular data. However, fraud detection requires evaluating recursive, multi-hop relationship patterns—such as detecting whether a new user shares a device with another account that previously committed fraud 2 or 3 hops away through a shared IP or bank account.
- In PostgreSQL, multi-hop traversals require multiple recursive `JOIN`s or recursive CTEs, which degrade exponentially ($O(k^d)$ where $k$ is average degree and $d$ is depth) as table size grows.
- In Neo4j, relationships are first-class index-free adjacency pointers. Traversing relationships is an $O(1)$ pointer hop per edge regardless of total graph size, enabling sub-10ms topological risk checks."

---

## 2. SQL & Relational Engineering

### Q: Explain the window functions used in your analytical queries.
**A**:
"In `sql/queries/analytics.sql`, we calculate user velocity and rapid IP hopping using window frames:
```sql
COUNT(*) OVER(
    PARTITION BY user_id 
    ORDER BY timestamp 
    RANGE BETWEEN INTERVAL '5 MINUTE' PRECEDING AND CURRENT ROW
) AS tx_count_last_5min,
LAG(ip_address, 1) OVER(
    PARTITION BY user_id 
    ORDER BY timestamp
) AS prev_ip_address
```
- `PARTITION BY user_id ORDER BY timestamp RANGE BETWEEN INTERVAL '5 MINUTE' PRECEDING`: Computes a rolling transaction count over a sliding 5-minute time window per user.
- `LAG(ip_address, 1)`: Fetches the immediately preceding IP address for the user to detect rapid geographical jumps or IP rotation between consecutive charges."

---

### Q: What indexes did you create on the PostgreSQL `transactions` table and why?
**A**:
"We created targeted B-Tree indexes based on query access patterns:
1. `idx_tx_user_id (user_id)`: Accelerates user history lookups and foreign key joins.
2. `idx_tx_timestamp (timestamp DESC)`: Optimizes time-range scans and daily partition queries.
3. `idx_tx_device_id (device_id)` & `idx_tx_ip_address (ip_address)`: Accelerates entity collision searches.
4. `idx_blacklist_lookup (entity_type, entity_value) WHERE is_active = TRUE`: A **partial index** indexing only active blacklisted entries to keep index size minimal and cache-friendly."

---

## 3. Streaming & Distributed Processing

### Q: How do you handle duplicate events and late-arriving data in PySpark Streaming?
**A**:
"1. **Late-Arriving Data**: We configure event-time watermarking (`withWatermark('timestamp', '10 minutes')`). Spark maintains state for in-flight sliding windows for up to 10 minutes of event-time delay. Records arriving after the watermark threshold are dropped to prevent unbounded state store memory growth.
2. **Duplicate Events**: In the streaming micro-batch layer, transactions are written to PostgreSQL using idempotent primary key semantics. In the batch Lakehouse ETL, the Bronze -> Silver pipeline performs definitive deduplication using `row_number() OVER (PARTITION BY transaction_id ORDER BY timestamp DESC)`."

---

### Q: What causes a shuffle in Apache Spark and how do you optimize it?
**A**:
"A shuffle occurs when data needs to be redistributed across partitions, triggered by wide transformations such as `groupByKey()`, `join()`, `distinct()`, or `repartition()`.
To optimize:
- Use `reduceByKey` or declarative aggregation functions rather than `groupByKey`.
- Broadcast small dimension tables (e.g., risk rules or blacklist lookups) using `broadcast(dim_df)` to convert expensive shuffle joins into map-side hash joins.
- Set appropriate `spark.sql.shuffle.partitions` (configured to 4 for local execution, or $2 \times \text{total cores}$ in distributed clusters) to avoid skew and excessive small partition overhead."

---

## 4. Graph Modeling & Identity Resolution

### Q: How does RiskGraph detect synthetic identity rings in Neo4j?
**A**:
"Synthetic identity fraud involves fraudsters creating multiple accounts using variations of synthetic identities (e.g., different fake names) while sharing underlying physical assets (such as the same mobile device hardware fingerprint or IP subnet).
In RiskGraph:
1. When transactions are processed, nodes `(:User)` and `(:Device)` are linked with `[:USES_DEVICE]`.
2. Cypher queries group devices by distinct linked users:
```cypher
MATCH (d:Device)<-[:USES_DEVICE]-(u:User)
WITH d, collect(u.id) AS users, count(u) AS user_count
WHERE user_count >= 3
RETURN d.id AS shared_device_id, users AS ring_members, user_count AS ring_size;
```
3. If `user_count >= 3`, the device is flagged as an identity ring, and all associated users trigger `RULE_DEVICE_RING` (weight +45.0, resulting in `BLOCK` or `REVIEW`)."

---

## 5. In-Memory Velocity & Low-Latency API

### Q: How does the Redis sliding-window velocity tracker work?
**A**:
"In `src/risk_engine/velocity_service.py`, we implement a precise sliding window using Redis **Sorted Sets** (`ZSET`):
1. **Timestamp as Score**: When a transaction arrives at timestamp $T$, we use $T$ as the score in `vel:usr:<user_id>`.
2. **Atomic Sliding Eviction**: In a single Redis pipeline:
   - `ZREMRANGEBYSCORE key 0 (T - window_seconds)`: Evicts transactions older than the rolling window (e.g. 300 seconds).
   - `ZADD key {member: T}`: Adds the current transaction timestamp.
   - `ZCARD key`: Returns the exact number of transactions in the active window.
   - `EXPIRE key (window_seconds * 2)`: Sets TTL to prevent memory leaks.
This executes in under 1 millisecond and avoids the fixed-window boundary problem of simple counters."

---

## 6. Data Quality & Pipeline Governance

### Q: What happens when invalid data enters the pipeline?
**A**:
"RiskGraph implements a multi-stage defense:
1. **API / Ingestion Boundary**: Pydantic models validate data types, bounds (`amount > 0`), and required fields, rejecting malformed requests at the door with HTTP 422.
2. **Streaming Dead-Letter Queue (DLQ)**: Malformed or unparseable Kafka messages are redirected to `fraud.dlq` for offline inspection without stalling the main stream.
3. **Data Quality Gates in Airflow**: The `DataQualityRunner` runs 7 core validation checks between Bronze and Silver/Gold. If quality metrics drop below threshold (e.g. null keys or negative amounts), the Airflow DAG halts execution before corrupted data can reach the Gold feature marts or Neo4j."

---

## 7. Production AWS Deployment & Scaling

### Q: How would you migrate this local architecture to production AWS?
**A**:
| Local Component | Production AWS Equivalent | Scaling Strategy |
|---|---|---|
| **LocalStack S3** | **Amazon S3 (Glacier lifecycle)** | Partitioned Parquet lakehouse with S3 Intelligent-Tiering and Athena for ad-hoc SQL. |
| **Kafka (Docker)** | **Amazon MSK (Managed Streaming for Kafka)** | Multi-AZ cluster with auto-partition rebalancing and IAM authentication. |
| **PySpark (Local)** | **Amazon EMR on EKS or AWS Glue 4.0** | Auto-scaling worker nodes running spot instances for cost optimization. |
| **PostgreSQL** | **Amazon Aurora PostgreSQL Serverless v2** | Multi-AZ read replicas with automated connection pooling via RDS Proxy. |
| **Neo4j** | **Neo4j Aura Enterprise or Amazon Neptune** | Read-replicas for graph traversal serving and graph backup snapshots. |
| **Redis** | **Amazon ElastiCache for Redis (Cluster Mode)** | In-memory replication across Availability Zones with sub-millisecond p99 latency. |
| **FastAPI** | **AWS ECS Fargate or EKS** | Auto-scaled container tasks behind an Application Load Balancer with AWS WAF. |
| **Airflow** | **MWAA (Managed Workflows for Apache Airflow)** | CeleryExecutor distributed across AWS workers. |
