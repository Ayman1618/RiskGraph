import pytest

from src.common.models import TransactionStatus
from src.generator.generator import SyntheticEventGenerator


def test_generator_initialization():
    gen = SyntheticEventGenerator(num_legit_users=50, num_fraud_rings=2, ring_size=4)
    assert len(gen.legit_users) == 50
    assert len(gen.fraud_rings) == 2
    assert len(gen.fraud_rings[0]) == 4


def test_generate_single_event():
    gen = SyntheticEventGenerator(fraud_ratio=0.0)
    tx, ident = gen.generate_single_event()

    assert tx.transaction_id.startswith("tx_")
    assert tx.user_id.startswith("usr_")
    assert tx.amount > 0
    assert tx.currency == "USD"
    assert tx.status == TransactionStatus.COMPLETED
    assert ident is not None
    assert ident.user_id == tx.user_id
    assert "@" in ident.email


def test_generate_fraud_ring_event():
    gen = SyntheticEventGenerator(fraud_ratio=1.0)
    tx, ident = gen.generate_single_event()

    assert tx.amount > 0
    assert tx.metadata.get("is_synthetic_fraud") is True
    assert tx.metadata.get("fraud_type_injected") in [
        "ring",
        "velocity",
        "ato",
        "blacklist",
        "amount",
    ]


def test_generate_stream_bounded():
    gen = SyntheticEventGenerator(fraud_ratio=0.2)
    events = list(gen.generate_stream(rate_per_sec=0, max_events=25))
    assert len(events) == 25
    for tx, ident in events:
        assert tx.amount > 0
