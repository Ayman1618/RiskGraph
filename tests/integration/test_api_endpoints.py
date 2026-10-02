from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_db_connection
from src.api.main import app

client = TestClient(app)


def mock_db_connection():
    """Mock DB connection for tests that don't need real PostgreSQL."""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.execute = MagicMock()
    cursor.fetchone = MagicMock(return_value=None)
    conn.cursor = MagicMock(return_value=cursor)
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    yield conn


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "RiskGraph" in data["service"]


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    assert data["services"]["api"] == "UP"


def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "riskgraph" in response.text


def test_rules_endpoint():
    response = client.get("/api/v1/rules")
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) >= 5
    assert any(r["rule_id"] == "RULE_HIGH_AMOUNT" for r in rules)


def test_evaluate_transaction_endpoint():
    app.dependency_overrides[get_db_connection] = mock_db_connection
    try:
        payload = {
            "user_id": "usr_api_test_01",
            "amount": 125.00,
            "ip_address": "198.51.100.99",
            "device_id": "dev_api_01",
        }
        response = client.post("/api/v1/transactions/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "usr_api_test_01"
        assert data["decision"] in ["APPROVE", "REVIEW", "BLOCK"]
        assert "risk_score" in data
        assert "latency_ms" in data
    finally:
        app.dependency_overrides.clear()
