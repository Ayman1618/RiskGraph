import json
from typing import Optional

import psycopg2
import redis
from psycopg2.extras import RealDictCursor

from src.common.config import settings
from src.common.logger import get_logger
from src.graph.graph_analytics import GraphFraudAnalytics
from src.graph.graph_client import Neo4jClient
from src.risk_engine.evaluator import RiskEvaluator
from src.risk_engine.velocity_service import VelocityService

logger = get_logger("api_dependencies")

# Singleton service instances
_neo4j_client: Optional[Neo4jClient] = None
_graph_analytics: Optional[GraphFraudAnalytics] = None
_velocity_service: Optional[VelocityService] = None
_risk_evaluator: Optional[RiskEvaluator] = None


def get_neo4j_client() -> Neo4jClient:
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client


def get_graph_analytics() -> GraphFraudAnalytics:
    global _graph_analytics
    if _graph_analytics is None:
        _graph_analytics = GraphFraudAnalytics(client=get_neo4j_client())
    return _graph_analytics


def get_velocity_service() -> VelocityService:
    global _velocity_service
    if _velocity_service is None:
        _velocity_service = VelocityService()
    return _velocity_service


def get_risk_evaluator() -> RiskEvaluator:
    global _risk_evaluator
    if _risk_evaluator is None:
        _risk_evaluator = RiskEvaluator(
            velocity_service=get_velocity_service(), graph_analytics=get_graph_analytics()
        )
    return _risk_evaluator


def get_db_connection():
    """
    Yields or returns a PostgreSQL connection.
    """
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        cursor_factory=RealDictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()
