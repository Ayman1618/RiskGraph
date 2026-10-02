-- ==========================================================
-- RiskGraph Analytical SQL Queries & Fraud Investigation Marts
-- ==========================================================

-- 1. Velocity Analysis: Users with rapid burst transactions using Window Functions
-- Demonstrates: Window frames, PARTITION BY, rolling count and cumulative amount
WITH ranked_transactions AS (
    SELECT
        transaction_id,
        user_id,
        amount,
        timestamp,
        COUNT(*) OVER(
            PARTITION BY user_id 
            ORDER BY timestamp 
            RANGE BETWEEN INTERVAL '5 MINUTE' PRECEDING AND CURRENT ROW
        ) AS tx_count_last_5min,
        SUM(amount) OVER(
            PARTITION BY user_id 
            ORDER BY timestamp 
            RANGE BETWEEN INTERVAL '5 MINUTE' PRECEDING AND CURRENT ROW
        ) AS sum_amount_last_5min,
        LAG(ip_address, 1) OVER(
            PARTITION BY user_id 
            ORDER BY timestamp
        ) AS prev_ip_address,
        ip_address AS curr_ip_address
    FROM transactions
)
SELECT
    transaction_id,
    user_id,
    amount,
    timestamp,
    tx_count_last_5min,
    sum_amount_last_5min,
    prev_ip_address,
    curr_ip_address,
    CASE 
        WHEN prev_ip_address IS NOT NULL AND prev_ip_address <> curr_ip_address THEN TRUE 
        ELSE FALSE 
    END AS is_rapid_ip_switch
FROM ranked_transactions
WHERE tx_count_last_5min >= 3
ORDER BY sum_amount_last_5min DESC;

-- 2. Multi-User Device Sharing (Device Fingerprint Collision)
-- Identifies potential synthetic identity rings sharing device hardware
SELECT
    d.device_id,
    d.device_fingerprint,
    d.is_emulator,
    COUNT(DISTINCT t.user_id) AS distinct_users_count,
    ARRAY_AGG(DISTINCT t.user_id) AS linked_user_ids,
    COUNT(t.transaction_id) AS total_transactions,
    SUM(t.amount) AS total_volume_attempted,
    COUNT(CASE WHEN t.decision = 'BLOCK' THEN 1 END) AS blocked_tx_count
FROM devices d
JOIN transactions t ON d.device_id = t.device_id
GROUP BY d.device_id, d.device_fingerprint, d.is_emulator
HAVING COUNT(DISTINCT t.user_id) > 1
ORDER BY distinct_users_count DESC, total_volume_attempted DESC;

-- 3. Daily Fraud Funnel & Rule Trigger Attribution
-- Calculates Approval Rate, Review Rate, Block Rate, and top triggered rules
SELECT
    DATE_TRUNC('day', timestamp) AS tx_date,
    COUNT(*) AS total_transactions,
    ROUND(SUM(amount), 2) AS gross_merchandise_volume,
    COUNT(CASE WHEN decision = 'APPROVE' THEN 1 END) AS approved_count,
    COUNT(CASE WHEN decision = 'REVIEW' THEN 1 END) AS review_count,
    COUNT(CASE WHEN decision = 'BLOCK' THEN 1 END) AS blocked_count,
    ROUND(100.0 * COUNT(CASE WHEN decision = 'BLOCK' THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS block_rate_pct,
    ROUND(AVG(risk_score), 2) AS avg_risk_score
FROM transactions
GROUP BY DATE_TRUNC('day', timestamp)
ORDER BY tx_date DESC;

-- 4. IP-Subnet Multi-Account Infiltration Analysis
SELECT
    ip_address,
    COUNT(DISTINCT user_id) AS unique_accounts,
    COUNT(DISTINCT card_token) AS unique_cards_used,
    SUM(amount) AS total_amount,
    AVG(risk_score) AS avg_ip_risk_score,
    COUNT(CASE WHEN decision = 'BLOCK' THEN 1 END) AS blocked_count
FROM transactions
GROUP BY ip_address
HAVING COUNT(DISTINCT user_id) >= 3
ORDER BY unique_accounts DESC;
