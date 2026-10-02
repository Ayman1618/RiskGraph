-- ==========================================================
-- RiskGraph Seed Fraud Rules & Initial Blacklist Data
-- ==========================================================

INSERT INTO risk_rules (rule_id, rule_name, description, category, weight, threshold, action, is_active)
VALUES
    ('RULE_HIGH_AMOUNT', 'High Transaction Amount', 'Transaction amount exceeds standard individual threshold', 'AMOUNT', 25.0, 5000.0, 'REVIEW', TRUE),
    ('RULE_CRITICAL_AMOUNT', 'Critical Transaction Amount', 'Transaction amount exceeds maximum single authorization threshold', 'AMOUNT', 50.0, 15000.0, 'BLOCK', TRUE),
    ('RULE_TX_VELOCITY_5M', 'High Velocity (5m)', 'More than 4 transactions from the same user within a 5-minute window', 'VELOCITY', 30.0, 4.0, 'REVIEW', TRUE),
    ('RULE_CARD_VELOCITY_10M', 'High Card Usage Velocity (10m)', 'More than 3 distinct users attempted on the same card within 10 minutes', 'VELOCITY', 40.0, 3.0, 'BLOCK', TRUE),
    ('RULE_DEVICE_RING', 'Shared Device Ring', 'Device is shared across 3 or more distinct user IDs', 'GRAPH', 45.0, 3.0, 'BLOCK', TRUE),
    ('RULE_IP_SUBNET_RISK', 'High-Risk Shared IP Subnet', 'More than 5 distinct users operating simultaneously from the same IP', 'GRAPH', 25.0, 5.0, 'REVIEW', TRUE),
    ('RULE_GRAPH_MULE_DISTANCE', 'Proximity to Confirmed Fraud Node', 'User is within 1 hop of a confirmed fraudulent node in identity graph', 'GRAPH', 50.0, 1.0, 'BLOCK', TRUE),
    ('RULE_EMULATOR_DEVICE', 'Emulator or Rooted Device Detected', 'Device signals indicate an Android emulator or rooted environment', 'DEVICE', 35.0, 1.0, 'REVIEW', TRUE),
    ('RULE_BLACKLIST_HIT', 'Blacklisted Entity Match', 'Direct match on blacklisted IP, card token, email, or device fingerprint', 'BLACKLIST', 100.0, 1.0, 'BLOCK', TRUE)
ON CONFLICT (rule_id) DO UPDATE SET
    rule_name = EXCLUDED.rule_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    weight = EXCLUDED.weight,
    threshold = EXCLUDED.threshold,
    action = EXCLUDED.action,
    is_active = EXCLUDED.is_active;

-- Seed known malicious entities for simulation and testing
INSERT INTO blacklisted_entities (entity_type, entity_value, reason, severity, is_active)
VALUES
    ('IP', '198.51.100.42', 'Known bulletproof proxy / TOR exit node associated with credential stuffing', 'CRITICAL', TRUE),
    ('IP', '203.0.113.88', 'Command and control botnet cluster', 'CRITICAL', TRUE),
    ('DEVICE', 'fp_emul_999a888b777c', 'Identified Nox/BlueStacks device spoofing farm', 'HIGH', TRUE),
    ('CARD', 'tok_card_fraud_stolen_411111', 'Confirmed compromised BIN range reported by issuer', 'CRITICAL', TRUE),
    ('EMAIL', 'fraud_ring_master@tempinbox.fake', 'Synthetic identity coordinator account', 'CRITICAL', TRUE)
ON CONFLICT (entity_type, entity_value) DO NOTHING;
