import json
import time
from typing import Any, Dict, List, Optional
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
    description="Synchronously evaluates transaction for fraud rules, velocity, and graph identity signals."
)
def evaluate_transaction(
    request: RiskEvaluationRequest,
    evaluator: RiskEvaluator = Depends(get_risk_evaluator),
):
    try:
        response = evaluator.evaluate(request)
        return response
    except Exception as e:
        logger.error(f"Failed to evaluate transaction: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation engine error: {str(e)}"
        )


@router.post(
    "/transactions/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Asynchronous Transaction Ingestion to Kafka",
    description="Ingests transaction event into Kafka raw ingestion stream."
)
def ingest_transaction(event: TransactionEvent):
    try:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None
        )
        producer.send(
            topic=settings.KAFKA_RAW_TRANSACTIONS_TOPIC,
            key=event.user_id,
            value=event.model_dump()
        )
        producer.flush()
        producer.close()
        TRANSACTIONS_INGESTED_TOTAL.labels(status="success").inc()
        return {"status": "QUEUED", "transaction_id": event.transaction_id, "topic": settings.KAFKA_RAW_TRANSACTIONS_TOPIC}
    except Exception as e:
        logger.warning(f"Kafka direct ingestion fallback (Kafka might be unavailable in local unit test): {e}")
        TRANSACTIONS_INGESTED_TOTAL.labels(status="fallback").inc()
        return {"status": "ACCEPTED_LOCAL", "transaction_id": event.transaction_id, "message": str(e)}


@router.get(
    "/entities/graph/{user_id}",
    summary="Get User Identity Subgraph",
    description="Extracts multi-hop identity graph neighborhood (Devices, IPs, Cards) for visual investigation."
)
def get_user_subgraph(
    user_id: str,
    depth: int = Query(default=2, ge=1, le=4),
    analytics: GraphFraudAnalytics = Depends(get_graph_analytics)
):
    subgraph = analytics.get_user_subgraph(user_id=user_id, depth=depth)
    return subgraph


@router.get(
    "/entities/rings",
    summary="Discover Identity Fraud Rings",
    description="Queries Neo4j for clusters of users sharing device hardware or cards."
)
def get_fraud_rings(
    min_size: int = Query(default=3, ge=2, le=20),
    analytics: GraphFraudAnalytics = Depends(get_graph_analytics)
):
    rings = analytics.find_fraud_rings(min_ring_size=min_size)
    return {"fraud_rings_count": len(rings), "rings": rings}


@router.get(
    "/risk/stats",
    summary="Platform Operational Fraud Statistics",
    description="Aggregates transaction volumes, approval/block rates, and GMV from PostgreSQL."
)
def get_risk_stats(conn=Depends(get_db_connection)):
    try:
        with conn.cursor() as cur:
            query = """
            SELECT 
                COUNT(*) AS total_transactions,
                COALESCE(SUM(amount), 0.0) AS total_gmv,
                COUNT(CASE WHEN decision = 'APPROVE' THEN 1 END) AS approved_count,
                COUNT(CASE WHEN decision = 'REVIEW' THEN 1 END) AS review_count,
                COUNT(CASE WHEN decision = 'BLOCK' THEN 1 END) AS blocked_count,
                ROUND(AVG(risk_score), 2) AS avg_risk_score
            FROM transactions;
            """
            cur.execute(query)
            row = cur.fetchone()
            
            total = row["total_transactions"] or 0
            blocked = row["blocked_count"] or 0
            block_rate = round(100.0 * blocked / total, 2) if total > 0 else 0.0

            return {
                "total_transactions": total,
                "total_gmv": float(row["total_gmv"]),
                "approved_count": row["approved_count"],
                "review_count": row["review_count"],
                "blocked_count": blocked,
                "block_rate_pct": block_rate,
                "avg_risk_score": float(row["avg_risk_score"] or 0.0)
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
            "note": "PostgreSQL not connected or empty"
        }


@router.get(
    "/rules",
    summary="Active Fraud Scoring Rules",
    description="Returns list of currently configured risk rules and weights."
)
def get_rules():
    return [
        {
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "category": r.category,
            "weight": r.weight,
            "description": r.description,
            "threshold": r.threshold
        }
        for r in DEFAULT_RULES.values()
    ]
