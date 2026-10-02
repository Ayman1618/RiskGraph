from typing import Any, Dict, List, Optional

from src.common.models import GraphFeatures, RiskEvaluationRequest, TriggeredRule


class RuleDefinition:
    def __init__(
        self,
        rule_id: str,
        rule_name: str,
        category: str,
        weight: float,
        description: str,
        threshold: float,
    ):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.category = category
        self.weight = weight
        self.description = description
        self.threshold = threshold


DEFAULT_RULES = {
    "RULE_HIGH_AMOUNT": RuleDefinition(
        rule_id="RULE_HIGH_AMOUNT",
        rule_name="High Transaction Amount",
        category="AMOUNT",
        weight=25.0,
        description="Amount exceeds normal threshold ($5,000)",
        threshold=5000.0,
    ),
    "RULE_CRITICAL_AMOUNT": RuleDefinition(
        rule_id="RULE_CRITICAL_AMOUNT",
        rule_name="Critical Transaction Amount",
        category="AMOUNT",
        weight=50.0,
        description="Amount exceeds maximum threshold ($15,000)",
        threshold=15000.0,
    ),
    "RULE_TX_VELOCITY_5M": RuleDefinition(
        rule_id="RULE_TX_VELOCITY_5M",
        rule_name="High Velocity (5m)",
        category="VELOCITY",
        weight=30.0,
        description="More than 4 transactions in 5 minutes",
        threshold=4.0,
    ),
    "RULE_DEVICE_RING": RuleDefinition(
        rule_id="RULE_DEVICE_RING",
        rule_name="Shared Device Ring",
        category="GRAPH",
        weight=45.0,
        description="Device is linked to 3 or more distinct users",
        threshold=3.0,
    ),
    "RULE_IP_SUBNET_RISK": RuleDefinition(
        rule_id="RULE_IP_SUBNET_RISK",
        rule_name="High-Risk Shared IP Subnet",
        category="GRAPH",
        weight=25.0,
        description="5 or more users operating from same IP",
        threshold=5.0,
    ),
    "RULE_GRAPH_MULE_DISTANCE": RuleDefinition(
        rule_id="RULE_GRAPH_MULE_DISTANCE",
        rule_name="Proximity to Confirmed Fraud Node",
        category="GRAPH",
        weight=50.0,
        description="User is within 1 hop of known fraudulent entity",
        threshold=1.0,
    ),
    "RULE_EMULATOR_DEVICE": RuleDefinition(
        rule_id="RULE_EMULATOR_DEVICE",
        rule_name="Emulator or Rooted Device",
        category="DEVICE",
        weight=35.0,
        description="Device signals indicate emulator/jailbreak",
        threshold=1.0,
    ),
    "RULE_BLACKLIST_HIT": RuleDefinition(
        rule_id="RULE_BLACKLIST_HIT",
        rule_name="Blacklist Hit",
        category="BLACKLIST",
        weight=100.0,
        description="Direct match against active blacklist registry",
        threshold=1.0,
    ),
}
