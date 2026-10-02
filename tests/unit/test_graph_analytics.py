from unittest.mock import MagicMock
import pytest
from src.graph.graph_analytics import GraphFraudAnalytics


def test_graph_analytics_safe_fallback():
    mock_client = MagicMock()
    mock_client.get_driver.side_effect = Exception("Neo4j not reachable in mock test")

    analytics = GraphFraudAnalytics(client=mock_client)
    feats = analytics.get_user_graph_features(user_id="usr_test_fallback")

    assert feats.user_id == "usr_test_fallback"
    assert feats.shared_device_count == 0
    assert feats.is_identity_ring_member is False


def test_graph_analytics_parsed_features():
    mock_client = MagicMock()
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_client.get_driver.return_value = mock_driver
    mock_driver.session.return_value.__enter__.return_value = mock_session

    mock_record = {
        "shared_device_count": 4,
        "shared_ip_count": 6,
        "shared_card_count": 1,
        "min_hop_to_fraud": 1,
        "connected_fraud_node_ids": ["usr_fraud_ring_leader"]
    }
    mock_result = MagicMock()
    mock_result.single.return_value = mock_record
    mock_session.run.return_value = mock_result

    analytics = GraphFraudAnalytics(client=mock_client)
    feats = analytics.get_user_graph_features(user_id="usr_ring_member_1")

    assert feats.shared_device_count == 4
    assert feats.shared_ip_count == 6
    assert feats.is_identity_ring_member is True
    assert feats.connected_fraud_node_ids == ["usr_fraud_ring_leader"]
