from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.api.routes import router
from src.common.config import settings
from src.common.logger import get_logger

logger = get_logger("api_main")

app = FastAPI(
    title="RiskGraph Platform API",
    description="Real-Time Fraud & Identity Data Engineering and Decision Engine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for developer UI/dashboard integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 routes
app.include_router(router)


@app.get("/", summary="Root Endpoint")
def root():
    return {
        "service": "RiskGraph Real-Time Fraud & Identity Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }


@app.get("/health", summary="Health Check")
def health_check():
    """
    Evaluates availability of platform components.
    """
    health_status = {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "services": {
            "api": "UP",
            "postgres": "UNKNOWN",
            "redis": "UNKNOWN",
            "neo4j": "UNKNOWN"
        }
    }

    # Check PostgreSQL
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            connect_timeout=2
        )
        conn.close()
        health_status["services"]["postgres"] = "UP"
    except Exception:
        health_status["services"]["postgres"] = "DOWN"

    # Check Redis
    try:
        import redis
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            socket_connect_timeout=2
        )
        r.ping()
        health_status["services"]["redis"] = "UP"
    except Exception:
        health_status["services"]["redis"] = "DOWN"

    # Check Neo4j
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        driver.verify_connectivity()
        driver.close()
        health_status["services"]["neo4j"] = "UP"
    except Exception:
        health_status["services"]["neo4j"] = "DOWN"

    return health_status


@app.get("/metrics", summary="Prometheus Metrics Exporter")
def metrics():
    """
    Exports Prometheus runtime metrics.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=settings.APP_PORT, reload=True)
