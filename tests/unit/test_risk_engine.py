import pytest
from unittest.mock import MagicMock

from src.common.models import GraphFeatures, RiskDecision, RiskEvaluationRequest
from src.risk_engine.evaluator import RiskEvaluator


@pytest.fixture
def mock_velocity_service():
    mock = MagicMock()
    mock.record_and_get_velocity.return_value = 1
    mock.get_blacklist_match.return_value = False
    return mock


@pytest.fixture
def mock_graph_analytics():
    mock = MagicMock()
    mock.get_user_graph_features.return_value = GraphFeatures(
        user_id="usr_test_123",
        shared_device_count=0,
        shared_ip_count=0,
        shared_card_count=0
    )
    return mock


def test_standard_transaction_approved(mock_velocity_service, mock_graph_analytics):
    evaluator = RiskEvaluator(
        velocity_service=mock_velocity_service,
        graph_analytics=mock_graph_analytics
    )

    req = RiskEvaluationRequest(
        user_id="usr_test_123",
        amount=45.50,
        ip_address="198.51.100.1",
        device_id="dev_legit_001"
    )

    resp = evaluator.evaluate(req)
    assert resp.decision == RiskDecision.APPROVE
    assert resp.risk_score < 35.0
    assert len(resp.triggered_rules) == 0


def test_critical_amount_blocked(mock_velocity_service, mock_graph_analytics):
    evaluator = RiskEvaluator(
        velocity_service=mock_velocity_service,
        graph_analytics=mock_graph_analytics
    )

    req = RiskEvaluationRequest(
        user_id="usr_test_123",
        amount=25000.0,
        ip_address="198.51.100.1"
    )

    resp = evaluator.evaluate(req)
    assert resp.decision == RiskDecision.BLOCK
    assert any(r.rule_id == "RULE_CRITICAL_AMOUNT" for r in resp.triggered_rules)


def test_high_velocity_review(mock_velocity_service, mock_graph_analytics):
    mock_velocity_service.record_and_get_velocity.return_value = 6  # Exceeds threshold of 4

    evaluator = RiskEvaluator(
        velocity_service=mock_velocity_service,
        graph_analytics=mock_graph_analytics
    )

    req = RiskEvaluationRequest(
        user_id="usr_velocity_spammer",
        amount=100.0,
        ip_address="198.51.100.1"
    )

    resp = evaluator.evaluate(req)
    assert resp.decision in [RiskDecision.REVIEW, RiskDecision.BLOCK]
    assert any(r.rule_id == "RULE_TX_VELOCITY_5M" for r in resp.triggered_rules)


def test_identity_ring_blocked(mock_velocity_service, mock_graph_analytics):
    mock_graph_analytics.get_user_graph_features.return_value = GraphFeatures(
        user_id="usr_ring_member",
        shared_device_count=4,
        is_identity_ring_member=True
    )

    evaluator = RiskEvaluator(
        velocity_service=mock_velocity_service,
        graph_analytics=mock_graph_analytics
    )

    req = RiskEvaluationRequest(
        user_id="usr_ring_member",
        amount=500.0,
        ip_address="192.0.2.10",
        device_id="dev_shared_ring_0"
    )

    resp = evaluator.evaluate(req)
    assert resp.decision == RiskDecision.BLOCK
    assert any(r.rule_id == "RULE_DEVICE_RING" for r in resp.triggered_rules)


def test_blacklist_match_blocked(mock_velocity_service, mock_graph_analytics):
    evaluator = RiskEvaluator(
        velocity_service=mock_velocity_service,
        graph_analytics=mock_graph_analytics
    )

    req = RiskEvaluationRequest(
        user_id="usr_known_attacker",
        amount=10.0,
        ip_address="198.51.100.42"  # Known blacklisted IP
    )

    resp = evaluator.evaluate(req)
    assert resp.decision == RiskDecision.BLOCK
    assert any(r.rule_id == "RULE_BLACKLIST_HIT" for r in resp.triggered_rules)
