import time
import uuid
from typing import List, Optional, Tuple

from src.common.logger import get_logger
from src.common.metrics import (
    RISK_EVALUATION_LATENCY_SECONDS,
    RISK_SCORE_HISTOGRAM,
    RULES_TRIGGERED_TOTAL,
    TRANSACTION_DECISIONS_TOTAL,
)
from src.common.models import (
    GraphFeatures,
    RiskDecision,
    RiskEvaluationRequest,
    RiskEvaluationResponse,
    TriggeredRule,
)
from src.graph.graph_analytics import GraphFraudAnalytics
from src.risk_engine.rules import DEFAULT_RULES
from src.risk_engine.velocity_service import VelocityService

logger = get_logger("risk_evaluator")


class RiskEvaluator:
    """
    Production Real-Time Fraud & Identity Risk Decision Engine.
    Combines rule weights, real-time velocity, Neo4j identity graph features, and blacklists.
    """

    def __init__(
        self,
        velocity_service: Optional[VelocityService] = None,
        graph_analytics: Optional[GraphFraudAnalytics] = None,
    ):
        self.velocity_service = velocity_service or VelocityService()
        self.graph_analytics = graph_analytics or GraphFraudAnalytics()

        # Static in-memory fallback blacklist for zero-latency lookups
        self.blacklisted_ips = {"198.51.100.42", "203.0.113.88"}
        self.blacklisted_devices = {"fp_emul_999a888b777c"}
        self.blacklisted_cards = {"tok_card_fraud_stolen_411111"}

    def evaluate(self, req: RiskEvaluationRequest) -> RiskEvaluationResponse:
        start_time = time.perf_counter()
        tx_id = req.transaction_id or f"tx_{uuid.uuid4().hex[:14]}"

        triggered_rules: List[TriggeredRule] = []
        reasons: List[str] = []

        # 1. Amount-based Rules
        if req.amount >= DEFAULT_RULES["RULE_CRITICAL_AMOUNT"].threshold:
            r = DEFAULT_RULES["RULE_CRITICAL_AMOUNT"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=r.threshold,
                    actual_value=req.amount,
                )
            )
            reasons.append(f"Critical amount threshold exceeded: ${req.amount:,.2f}")
        elif req.amount >= DEFAULT_RULES["RULE_HIGH_AMOUNT"].threshold:
            r = DEFAULT_RULES["RULE_HIGH_AMOUNT"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=r.threshold,
                    actual_value=req.amount,
                )
            )
            reasons.append(f"High amount threshold exceeded: ${req.amount:,.2f}")

        # 2. Redis Real-Time Velocity
        vel_5m = self.velocity_service.record_and_get_velocity(
            entity_key=f"usr:{req.user_id}", window_seconds=300, amount=req.amount
        )
        if vel_5m > DEFAULT_RULES["RULE_TX_VELOCITY_5M"].threshold:
            r = DEFAULT_RULES["RULE_TX_VELOCITY_5M"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=r.threshold,
                    actual_value=float(vel_5m),
                )
            )
            reasons.append(f"High user velocity: {vel_5m} transactions in 5 minutes")

        # 3. Device Signals
        if req.is_emulator or req.is_rooted:
            r = DEFAULT_RULES["RULE_EMULATOR_DEVICE"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=1.0,
                    actual_value=1.0,
                )
            )
            reasons.append("Device integrity compromised (emulator or rooted device detected)")

        # 4. Blacklist Check
        is_blacklisted = (
            req.ip_address in self.blacklisted_ips
            or (req.device_fingerprint and req.device_fingerprint in self.blacklisted_devices)
            or (req.card_token and req.card_token in self.blacklisted_cards)
            or self.velocity_service.get_blacklist_match("IP", req.ip_address)
            or self.velocity_service.get_blacklist_match("DEVICE", req.device_fingerprint or "")
            or self.velocity_service.get_blacklist_match("CARD", req.card_token or "")
        )

        if is_blacklisted:
            r = DEFAULT_RULES["RULE_BLACKLIST_HIT"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=1.0,
                    actual_value=1.0,
                )
            )
            reasons.append("Entity matched known malicious blacklist registry")

        # 5. Graph Features (Neo4j)
        graph_feats = self.graph_analytics.get_user_graph_features(req.user_id)

        if graph_feats.shared_device_count >= DEFAULT_RULES["RULE_DEVICE_RING"].threshold:
            r = DEFAULT_RULES["RULE_DEVICE_RING"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=r.threshold,
                    actual_value=float(graph_feats.shared_device_count),
                )
            )
            reasons.append(
                f"Synthetic identity ring: Device shared across {graph_feats.shared_device_count} users"
            )

        if graph_feats.shared_ip_count >= DEFAULT_RULES["RULE_IP_SUBNET_RISK"].threshold:
            r = DEFAULT_RULES["RULE_IP_SUBNET_RISK"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=r.threshold,
                    actual_value=float(graph_feats.shared_ip_count),
                )
            )
            reasons.append(f"IP subnet risk: Shared across {graph_feats.shared_ip_count} users")

        if graph_feats.hop_distance_to_fraud is not None and graph_feats.hop_distance_to_fraud <= 1:
            r = DEFAULT_RULES["RULE_GRAPH_MULE_DISTANCE"]
            triggered_rules.append(
                TriggeredRule(
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    category=r.category,
                    weight=r.weight,
                    description=r.description,
                    threshold=r.threshold,
                    actual_value=float(graph_feats.hop_distance_to_fraud),
                )
            )
            reasons.append(
                f"Immediate proximity (1 hop) to confirmed fraud node {graph_feats.connected_fraud_node_ids}"
            )

        # Calculate Total Weighted Score (Capped at 100.0)
        total_weight = sum(rule.weight for rule in triggered_rules)
        risk_score = min(100.0, total_weight)

        # Decision Logic
        if (
            is_blacklisted
            or any(
                r.rule_id in ["RULE_CRITICAL_AMOUNT", "RULE_GRAPH_MULE_DISTANCE"]
                for r in triggered_rules
            )
            or (graph_feats.shared_device_count >= 3 and graph_feats.is_identity_ring_member)
            or risk_score >= 80.0
        ):
            decision = RiskDecision.BLOCK
        elif risk_score >= 25.0 or any(
            r.rule_id
            in [
                "RULE_HIGH_AMOUNT",
                "RULE_TX_VELOCITY_5M",
                "RULE_EMULATOR_DEVICE",
                "RULE_IP_SUBNET_RISK",
            ]
            for r in triggered_rules
        ):
            decision = RiskDecision.REVIEW
        else:
            decision = RiskDecision.APPROVE
            if not reasons:
                reasons.append("Standard transaction parameters within normal thresholds")

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Track Prometheus Telemetry
        try:
            TRANSACTION_DECISIONS_TOTAL.labels(decision=decision.value).inc()
            RISK_SCORE_HISTOGRAM.observe(risk_score)
            RISK_EVALUATION_LATENCY_SECONDS.observe(latency_ms / 1000.0)
            for r in triggered_rules:
                RULES_TRIGGERED_TOTAL.labels(rule_id=r.rule_id, category=r.category).inc()
        except Exception:
            pass

        return RiskEvaluationResponse(
            transaction_id=tx_id,
            user_id=req.user_id,
            risk_score=round(risk_score, 2),
            decision=decision,
            reasons=reasons,
            triggered_rules=triggered_rules,
            graph_features=graph_feats,
            velocity_5m_count=vel_5m,
            latency_ms=latency_ms,
        )
