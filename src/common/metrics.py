from prometheus_client import Counter, Histogram, Gauge

# Transaction Ingestion Metrics
TRANSACTIONS_INGESTED_TOTAL = Counter(
    "riskgraph_transactions_ingested_total",
    "Total number of raw transactions received by the platform",
    ["status"]
)

# Real-Time Decision Metrics
TRANSACTION_DECISIONS_TOTAL = Counter(
    "riskgraph_decisions_total",
    "Total fraud risk evaluation decisions rendered",
    ["decision"]
)

# Triggered Rules Counter
RULES_TRIGGERED_TOTAL = Counter(
    "riskgraph_rules_triggered_total",
    "Count of individual fraud rules triggered during evaluation",
    ["rule_id", "category"]
)

# Risk Score Distribution
RISK_SCORE_HISTOGRAM = Histogram(
    "riskgraph_risk_score_distribution",
    "Distribution of calculated risk scores (0-100)",
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
)

# Scoring Latency
RISK_EVALUATION_LATENCY_SECONDS = Histogram(
    "riskgraph_evaluation_latency_seconds",
    "Latency of end-to-end risk evaluation in seconds",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# Active Fraud Alerts Gauge
ACTIVE_FRAUD_ALERTS = Gauge(
    "riskgraph_active_fraud_alerts",
    "Current count of open/unresolved fraud alerts",
    ["severity"]
)

# Spark Streaming & Batch Lag
STREAMING_BATCH_PROCESSING_TIME = Histogram(
    "riskgraph_spark_streaming_batch_duration_seconds",
    "Spark Structured Streaming micro-batch execution duration in seconds"
)

STREAMING_RECORDS_PROCESSED_TOTAL = Counter(
    "riskgraph_spark_streaming_records_processed_total",
    "Total events processed by PySpark Structured Streaming",
    ["sink"]
)
