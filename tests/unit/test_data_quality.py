import pandas as pd
import pytest

from src.data_quality.dq_rules import (
    check_not_null,
    check_positive_amount,
    check_valid_enum,
    check_valid_ipv4,
)
from src.data_quality.dq_runner import DataQualityRunner


def test_dq_checks_pass():
    data = {
        "transaction_id": ["tx_1", "tx_2", "tx_3"],
        "user_id": ["u_1", "u_2", "u_3"],
        "amount": [10.50, 250.0, 99.99],
        "currency": ["USD", "USD", "EUR"],
        "ip_address": ["192.168.1.1", "10.0.0.1", "172.16.0.1"],
    }
    df = pd.DataFrame(data)

    runner = DataQualityRunner()
    report = runner.run_suite(df, dataset_name="clean_tx_test")

    assert report.is_dataset_healthy is True
    assert report.overall_pass_rate == 100.0
    assert report.failed_checks == 0


def test_dq_checks_detect_anomalies():
    bad_data = {
        "transaction_id": ["tx_1", None, "tx_3"],
        "user_id": ["u_1", "u_2", "u_3"],
        "amount": [10.50, -50.0, 99.99],  # Negative amount
        "currency": ["USD", "INVALID_CURRENCY", "EUR"],
        "ip_address": ["192.168.1.1", "NOT_AN_IP", "172.16.0.1"],
    }
    df = pd.DataFrame(bad_data)

    runner = DataQualityRunner()
    report = runner.run_suite(df, dataset_name="corrupt_tx_test")

    assert report.is_dataset_healthy is False
    assert report.failed_checks > 0
    assert report.overall_pass_rate < 100.0
