import json
import time
from datetime import datetime, timezone
from typing import List, Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import (
    get_db_connection,
    get_graph_analytics,
    get_risk_evaluator,
)
from src.common.config import settings
from src.common.logger import get_logger
from src.common.metrics import TRANSACTIONS_INGESTED_TOTAL
from src.common.models import (
    RiskEvaluationRequest,
    RiskEvaluationResponse,
    TransactionEvent,
)
from src.graph.graph_analytics import GraphFraudAnalytics
from src.risk_engine.evaluator import RiskEvaluator
from src.risk_engine.rules import DEFAULT_RULES

logger = get_logger("api_routes")
router = APIRouter(prefix="/api/v1")


@router.post(
    "/transactions/evaluate",
    response_model=RiskEvaluationResponse,
    summary="Real-Time Fraud Risk Evaluation",
    description="Synchronously evaluates transaction for fraud rules, velocity, and graph identity signals.",
)
def evaluate_transaction(
    request: RiskEvaluationRequest,
    evaluator: RiskEvaluator = Depends(get_risk_evaluator),
    conn=Depends(get_db_connection),
):
    try:
        response = evaluator.evaluate(request)

        # Write result to PostgreSQL so stats and listings work
        try:
            with conn.cursor() as cur:
                # Ensure user exists (upsert)
                cur.execute(
                    """
                    INSERT INTO users (user_id, email, phone, full_name)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (
                        request.user_id,
                        f"{request.user_id}@example.com",
                        "+10000000000",
                        f"User {request.user_id[:8]}",
                    ),
                )
                # Insert transaction
                cur.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id, user_id, amount, currency,
                        merchant_id, device_id, ip_address,
                        location_country, risk_score, decision,
                        triggered_rules, status, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'COMPLETED', NOW())
                    ON CONFLICT (transaction_id) DO NOTHING
                    """,
                    (
                        response.transaction_id,
                        request.user_id,
                        request.amount,
                        getattr(request, "currency", "USD"),
                        getattr(request, "merchant_id", None),
                        getattr(request, "device_id", None),
                        request.ip_address,
                        getattr(request, "country", None),
                        response.risk_score,
                        response.decision.value,
                        json.dumps([r.model_dump() for r in response.triggered_rules]),
                    ),
                )
                conn.commit()
        except Exception as db_err:
            logger.warning(f"DB write skipped: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass

        return response
    except Exception as e:
        logger.error(f"Failed to evaluate transaction: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation engine error: {str(e)}",
        )


@router.get(
    "/transactions",
    summary="List Transactions",
    description="Paginated list of evaluated transactions from PostgreSQL.",
)
def list_transactions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    decision: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    min_risk: Optional[float] = Query(default=None),
    max_risk: Optional[float] = Query(default=None),
    conn=Depends(get_db_connection),
):
    try:
        filters = []
        params: list = []

        if decision:
            filters.append("t.decision = %s")
            params.append(decision.upper())
        if search:
            filters.append(
                "(t.transaction_id ILIKE %s OR t.user_id ILIKE %s OR t.ip_address ILIKE %s OR t.device_id ILIKE %s)"
            )
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
        if min_risk is not None:
            filters.append("t.risk_score >= %s")
            params.append(min_risk)
        if max_risk is not None:
            filters.append("t.risk_score <= %s")
            params.append(max_risk)

        where = "WHERE " + " AND ".join(filters) if filters else ""

        with conn.cursor() as cur:
            # Total count
            cur.execute(f"SELECT COUNT(*) as cnt FROM transactions t {where}", params)
            total = cur.fetchone()["cnt"]

            # Fetch rows
            cur.execute(
                f"""
                SELECT
                    t.transaction_id, t.user_id, t.amount, t.currency,
                    t.merchant_id, t.device_id, t.ip_address,
                    t.location_country, t.risk_score, t.decision,
                    t.triggered_rules, t.status, t.timestamp,
                    u.full_name AS user_name
                FROM transactions t
                LEFT JOIN users u ON t.user_id = u.user_id
                {where}
                ORDER BY t.timestamp DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "transactions": [dict(r) for r in rows],
        }
    except Exception as e:
        logger.warning(f"Error listing transactions: {e}")
        return {"total": 0, "limit": limit, "offset": offset, "transactions": []}


@router.get(
    "/transactions/{transaction_id}",
    summary="Get Transaction Detail",
    description="Full transaction record with triggered rules and risk context.",
)
def get_transaction_detail(
    transaction_id: str,
    conn=Depends(get_db_connection),
):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    t.*, u.full_name AS user_name, u.email AS user_email
                FROM transactions t
                LEFT JOIN users u ON t.user_id = u.user_id
                WHERE t.transaction_id = %s
                """,
                (transaction_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Transaction not found")
            result = dict(row)
            # Ensure triggered_rules is a list (may be stored as JSON string)
            rules = result.get("triggered_rules", [])
            if isinstance(rules, str):
                try:
                    result["triggered_rules"] = json.loads(rules)
                except Exception:
                    result["triggered_rules"] = []

            # Fetch related transactions for the same user
            user_id = result.get("user_id")
            related = []
            if user_id:
                cur.execute(
                    """
                    SELECT transaction_id, timestamp, amount, currency, decision, risk_score, merchant_id
                    FROM transactions
                    WHERE user_id = %s AND transaction_id != %s
                    ORDER BY timestamp DESC
                    LIMIT 6
                    """,
                    (user_id, transaction_id),
                )
                related = [dict(r) for r in cur.fetchall()]
            result["related_transactions"] = related
            return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/transactions/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Asynchronous Transaction Ingestion to Kafka",
    description="Ingests transaction event into Kafka raw ingestion stream.",
)
def ingest_transaction(event: TransactionEvent):
    try:
        from kafka import KafkaProducer

        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        producer.send(
            topic=settings.KAFKA_RAW_TRANSACTIONS_TOPIC,
            key=event.user_id,
            value=event.model_dump(),
        )
        producer.flush()
        producer.close()
        TRANSACTIONS_INGESTED_TOTAL.labels(status="success").inc()
        return {
            "status": "QUEUED",
            "transaction_id": event.transaction_id,
            "topic": settings.KAFKA_RAW_TRANSACTIONS_TOPIC,
        }
    except Exception as e:
        logger.warning(f"Kafka direct ingestion fallback: {e}")
        TRANSACTIONS_INGESTED_TOTAL.labels(status="fallback").inc()
        return {
            "status": "ACCEPTED_LOCAL",
            "transaction_id": event.transaction_id,
            "message": str(e),
        }


@router.get(
    "/entities/graph/{user_id}",
    summary="Get User Identity Subgraph",
    description="Extracts multi-hop identity graph neighborhood for visual investigation.",
)
def get_user_subgraph(
    user_id: str,
    depth: int = Query(default=2, ge=1, le=4),
    analytics: GraphFraudAnalytics = Depends(get_graph_analytics),
    conn=Depends(get_db_connection),
):
    subgraph = analytics.get_user_subgraph(user_id=user_id, depth=depth)
    if not subgraph.get("edges") or len(subgraph.get("nodes", [])) <= 1:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT device_id, ip_address, merchant_id
                    FROM transactions
                    WHERE user_id = %s
                    LIMIT 8
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                if rows:
                    nodes = [{"id": user_id, "label": "User", "type": "User"}]
                    edges = []
                    seen_nodes = {user_id}
                    for r in rows:
                        dev = r.get("device_id")
                        ip = r.get("ip_address")
                        mch = r.get("merchant_id")
                        if dev and dev not in seen_nodes:
                            seen_nodes.add(dev)
                            nodes.append({"id": dev, "label": "Device", "type": "Device"})
                            edges.append({"source": user_id, "target": dev, "type": "USES_DEVICE"})
                        if ip and ip not in seen_nodes:
                            seen_nodes.add(ip)
                            nodes.append({"id": ip, "label": "IP", "type": "IP"})
                            edges.append(
                                {"source": user_id, "target": ip, "type": "ORIGINATED_FROM"}
                            )
                        if mch and mch not in seen_nodes:
                            seen_nodes.add(mch)
                            nodes.append({"id": mch, "label": "Merchant", "type": "Merchant"})
                            edges.append(
                                {"source": user_id, "target": mch, "type": "TRANSACTS_WITH"}
                            )
                    return {"user_id": user_id, "nodes": nodes, "edges": edges}
        except Exception as e:
            logger.debug(f"Transaction fallback for graph: {e}")
    return subgraph


@router.get(
    "/entities/rings",
    summary="Discover Identity Fraud Rings",
    description="Queries Neo4j for clusters of users sharing device hardware or cards.",
)
def get_fraud_rings(
    min_size: int = Query(default=3, ge=2, le=20),
    analytics: GraphFraudAnalytics = Depends(get_graph_analytics),
):
    rings = analytics.find_fraud_rings(min_ring_size=min_size)
    return {"fraud_rings_count": len(rings), "rings": rings}


@router.get(
    "/risk/stats",
    summary="Platform Operational Fraud Statistics",
    description="Aggregates transaction volumes, approval/block rates, and GMV from PostgreSQL.",
)
def get_risk_stats(conn=Depends(get_db_connection)):
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_transactions,
                    COALESCE(SUM(amount), 0.0) AS total_gmv,
                    COUNT(CASE WHEN decision = 'APPROVE' THEN 1 END) AS approved_count,
                    COUNT(CASE WHEN decision = 'REVIEW' THEN 1 END) AS review_count,
                    COUNT(CASE WHEN decision = 'BLOCK' THEN 1 END) AS blocked_count,
                    ROUND(AVG(risk_score), 2) AS avg_risk_score
                FROM transactions;
                """)
            row = cur.fetchone()
            total = row["total_transactions"] or 0
            blocked = row["blocked_count"] or 0
            block_rate = round(100.0 * blocked / total, 2) if total > 0 else 0.0

            # Hourly breakdown for last 24h
            cur.execute("""
                SELECT
                    date_trunc('hour', timestamp) AS hour,
                    COUNT(*) AS count,
                    COUNT(CASE WHEN decision = 'BLOCK' THEN 1 END) AS blocked
                FROM transactions
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
                GROUP BY hour
                ORDER BY hour DESC
                LIMIT 24
                """)
            hourly = [dict(r) for r in cur.fetchall()]

            return {
                "total_transactions": total,
                "total_gmv": float(row["total_gmv"]),
                "approved_count": row["approved_count"],
                "review_count": row["review_count"],
                "blocked_count": blocked,
                "block_rate_pct": block_rate,
                "avg_risk_score": float(row["avg_risk_score"] or 0.0),
                "hourly_breakdown": hourly,
            }
    except Exception as e:
        logger.warning(f"Error querying operational stats: {e}")
        return {
            "total_transactions": 0,
            "total_gmv": 0.0,
            "approved_count": 0,
            "review_count": 0,
            "blocked_count": 0,
            "block_rate_pct": 0.0,
            "avg_risk_score": 0.0,
            "hourly_breakdown": [],
        }


@router.get(
    "/dq/results",
    summary="Data Quality Results",
    description="Latest DQ check results from the DQ runner.",
)
def get_dq_results(conn=Depends(get_db_connection)):
    try:
        import pandas as pd

        from src.data_quality.dq_runner import DataQualityRunner
        from src.generator.generator import SyntheticEventGenerator

        gen = SyntheticEventGenerator()
        raw_events = []
        for tx, _ in gen.generate_stream(rate_per_sec=0.0, max_events=200):
            raw_events.append(tx.model_dump())
        df = pd.DataFrame(raw_events)
        runner = DataQualityRunner()
        report = runner.run_suite(df=df, dataset_name="live_transactions")

        return {
            "dataset": report.dataset_name,
            "total_records": report.total_records,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "pass_rate": round(report.overall_pass_rate * 100, 2),
            "checks": [
                {
                    "name": r.check_name,
                    "type": r.check_type,
                    "passed": r.passed,
                    "pass_rate": round(r.pass_rate * 100, 2),
                    "failed_count": r.failed_count,
                    "description": r.description,
                }
                for r in report.results
            ],
        }
    except Exception as e:
        logger.warning(f"DQ runner error: {e}")
        return {
            "dataset": "transactions",
            "total_records": 0,
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
            "pass_rate": 0.0,
            "checks": [],
            "error": str(e),
        }


@router.get(
    "/pipeline/status",
    summary="Pipeline Component Status",
    description="Real-time status of Kafka, PostgreSQL, Neo4j, Redis, and S3.",
)
def get_pipeline_status():
    import socket

    results = {}

    # Kafka
    try:
        from kafka import KafkaAdminClient

        admin = KafkaAdminClient(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
            request_timeout_ms=3000,
        )
        topics = admin.list_topics()
        admin.close()
        results["kafka"] = {
            "status": "HEALTHY",
            "topics": len(topics),
            "topic_names": list(topics)[:10],
        }
    except Exception as e:
        results["kafka"] = {"status": "DOWN", "error": str(e)[:100]}

    # PostgreSQL
    try:
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM transactions")
            tx_count = cur.fetchone()[0]
        conn.close()
        results["postgres"] = {"status": "HEALTHY", "transaction_count": tx_count}
    except Exception as e:
        results["postgres"] = {"status": "DOWN", "error": str(e)[:100]}

    # Neo4j
    try:
        import requests as req_lib

        r = req_lib.get("http://neo4j:7474/", timeout=3)
        results["neo4j"] = {"status": "HEALTHY" if r.status_code < 400 else "DEGRADED"}
    except Exception:
        try:
            s = socket.create_connection(("localhost", 7687), timeout=3)
            s.close()
            results["neo4j"] = {"status": "HEALTHY"}
        except Exception as e:
            results["neo4j"] = {"status": "DOWN", "error": str(e)[:80]}

    # Redis
    try:
        import redis as redis_lib

        r = redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            socket_connect_timeout=3,
        )
        r.ping()
        info = r.info()
        results["redis"] = {
            "status": "HEALTHY",
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "?"),
        }
    except Exception as e:
        results["redis"] = {"status": "DOWN", "error": str(e)[:100]}

    # LocalStack S3
    try:
        import requests as req_lib

        r = req_lib.get("http://localhost:4566/_localstack/health", timeout=3)
        h = r.json()
        s3_status = h.get("services", {}).get("s3", "unknown")
        results["s3"] = {
            "status": "HEALTHY" if s3_status == "running" else "DEGRADED",
            "localstack_s3": s3_status,
        }
    except Exception as e:
        results["s3"] = {"status": "UNKNOWN", "error": str(e)[:80]}

    # Airflow (optional)
    try:
        import requests as req_lib

        r = req_lib.get("http://localhost:8080/health", timeout=2)
        results["airflow"] = {"status": "HEALTHY" if r.status_code == 200 else "DEGRADED"}
    except Exception:
        results["airflow"] = {"status": "UNKNOWN", "note": "Not running locally"}

    return {"checked_at": datetime.now(timezone.utc).isoformat(), "components": results}


@router.get(
    "/rules",
    summary="Active Fraud Scoring Rules",
    description="Returns list of currently configured risk rules and weights.",
)
def get_rules():
    return [
        {
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "category": r.category,
            "weight": r.weight,
            "description": r.description,
            "threshold": r.threshold,
        }
        for r in DEFAULT_RULES.values()
    ]
