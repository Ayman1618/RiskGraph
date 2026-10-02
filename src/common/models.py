from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class RiskDecision(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class DeviceSignal(BaseModel):
    device_id: str
    device_fingerprint: str
    os: Optional[str] = "iOS"
    browser: Optional[str] = "Safari"
    is_emulator: bool = False
    is_rooted: bool = False
    screen_resolution: Optional[str] = "1170x2532"
    user_agent: Optional[str] = None


class IdentityEvent(BaseModel):
    user_id: str
    email: str
    phone: Optional[str] = None
    full_name: Optional[str] = None
    national_id: Optional[str] = None
    kyc_status: str = "VERIFIED"
    risk_tier: str = "STANDARD"
    device: Optional[DeviceSignal] = None
    ip_address: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransactionEvent(BaseModel):
    transaction_id: str
    user_id: str
    amount: float = Field(gt=0, description="Transaction amount in currency")
    currency: str = "USD"
    transaction_type: str = "PAYMENT"
    payment_method: str = "CARD"
    card_token: Optional[str] = None
    bank_account: Optional[str] = None
    merchant_id: Optional[str] = None
    device_id: Optional[str] = None
    ip_address: str
    location_country: Optional[str] = "US"
    location_city: Optional[str] = "New York"
    device_signals: Optional[DeviceSignal] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: TransactionStatus = TransactionStatus.COMPLETED
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TriggeredRule(BaseModel):
    rule_id: str
    rule_name: str
    category: str
    weight: float
    description: str
    threshold: Optional[float] = None
    actual_value: Optional[float] = None


class GraphFeatures(BaseModel):
    user_id: str
    shared_device_count: int = 0
    shared_ip_count: int = 0
    shared_card_count: int = 0
    hop_distance_to_fraud: Optional[int] = None
    community_id: Optional[str] = None
    pagerank_score: float = 0.0
    is_identity_ring_member: bool = False
    connected_fraud_node_ids: List[str] = Field(default_factory=list)


class RiskEvaluationRequest(BaseModel):
    transaction_id: Optional[str] = None
    user_id: str
    amount: float = Field(gt=0)
    currency: str = "USD"
    ip_address: str
    device_id: Optional[str] = None
    device_fingerprint: Optional[str] = None
    card_token: Optional[str] = None
    bank_account: Optional[str] = None
    merchant_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_emulator: bool = False
    is_rooted: bool = False
    timestamp: Optional[datetime] = None


class RiskEvaluationResponse(BaseModel):
    transaction_id: str
    user_id: str
    risk_score: float = Field(ge=0.0, le=100.0)
    decision: RiskDecision
    reasons: List[str]
    triggered_rules: List[TriggeredRule]
    graph_features: Optional[GraphFeatures] = None
    velocity_5m_count: int = 0
    latency_ms: float
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FraudAlert(BaseModel):
    alert_id: str
    transaction_id: str
    user_id: str
    severity: AlertSeverity
    risk_score: float
    decision: RiskDecision
    reasons: List[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
