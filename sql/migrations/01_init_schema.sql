-- ==========================================================
-- RiskGraph Operational Data Store (ODS) - Schema Migration 01
-- ==========================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enum Types
DO $$ BEGIN
    CREATE TYPE transaction_status AS ENUM ('PENDING', 'COMPLETED', 'FAILED', 'REVERSED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE risk_decision AS ENUM ('APPROVE', 'REVIEW', 'BLOCK');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE alert_severity AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE entity_type AS ENUM ('USER', 'DEVICE', 'IP', 'CARD', 'EMAIL', 'PHONE', 'BANK_ACCOUNT');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 1. Users Master Table
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(32),
    full_name VARCHAR(255),
    national_id VARCHAR(64),
    kyc_status VARCHAR(32) DEFAULT 'VERIFIED',
    risk_tier VARCHAR(32) DEFAULT 'STANDARD',
    account_created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_national_id ON users(national_id);

-- 2. Devices Master Table
CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(64) PRIMARY KEY,
    device_fingerprint VARCHAR(128) NOT NULL,
    os VARCHAR(64),
    browser VARCHAR(64),
    is_emulator BOOLEAN DEFAULT FALSE,
    is_rooted BOOLEAN DEFAULT FALSE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_fingerprint ON devices(device_fingerprint);

-- 3. Blacklisted Entities Table
CREATE TABLE IF NOT EXISTS blacklisted_entities (
    id SERIAL PRIMARY KEY,
    entity_type entity_type NOT NULL,
    entity_value VARCHAR(255) NOT NULL,
    reason TEXT NOT NULL,
    severity alert_severity NOT NULL DEFAULT 'HIGH',
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_entity_type_value UNIQUE (entity_type, entity_value)
);

CREATE INDEX IF NOT EXISTS idx_blacklist_lookup ON blacklisted_entities(entity_type, entity_value) WHERE is_active = TRUE;

-- 4. Transactions Operational Store
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount NUMERIC(15, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    transaction_type VARCHAR(32) NOT NULL DEFAULT 'PAYMENT',
    payment_method VARCHAR(32) NOT NULL DEFAULT 'CARD',
    card_token VARCHAR(64),
    bank_account VARCHAR(64),
    merchant_id VARCHAR(64),
    device_id VARCHAR(64),
    ip_address VARCHAR(45) NOT NULL,
    location_country VARCHAR(3),
    location_city VARCHAR(100),
    status transaction_status NOT NULL DEFAULT 'COMPLETED',
    risk_score NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    decision risk_decision NOT NULL DEFAULT 'APPROVE',
    triggered_rules JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tx_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tx_device_id ON transactions(device_id);
CREATE INDEX IF NOT EXISTS idx_tx_ip_address ON transactions(ip_address);
CREATE INDEX IF NOT EXISTS idx_tx_card_token ON transactions(card_token);
CREATE INDEX IF NOT EXISTS idx_tx_decision ON transactions(decision);
CREATE INDEX IF NOT EXISTS idx_tx_risk_score ON transactions(risk_score DESC);

-- 5. Real-Time Streaming Velocity Aggregates
CREATE TABLE IF NOT EXISTS streaming_velocity_aggregates (
    id SERIAL PRIMARY KEY,
    entity_type entity_type NOT NULL,
    entity_id VARCHAR(255) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    tx_count INT NOT NULL DEFAULT 0,
    total_amount NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    distinct_devices INT NOT NULL DEFAULT 0,
    distinct_ips INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_velocity_window UNIQUE (entity_type, entity_id, window_start, window_end)
);

CREATE INDEX IF NOT EXISTS idx_velocity_lookup ON streaming_velocity_aggregates(entity_type, entity_id, window_end DESC);

-- 6. Risk Rules Engine Configuration
CREATE TABLE IF NOT EXISTS risk_rules (
    rule_id VARCHAR(64) PRIMARY KEY,
    rule_name VARCHAR(128) NOT NULL,
    description TEXT,
    category VARCHAR(64) NOT NULL DEFAULT 'VELOCITY',
    weight NUMERIC(5, 2) NOT NULL DEFAULT 10.0,
    threshold NUMERIC(10, 2) NOT NULL DEFAULT 1.0,
    action risk_decision NOT NULL DEFAULT 'REVIEW',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Fraud Alerts for Investigation / Compliance
CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id VARCHAR(64) PRIMARY KEY,
    transaction_id VARCHAR(64) REFERENCES transactions(transaction_id) ON DELETE CASCADE,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    severity alert_severity NOT NULL DEFAULT 'MEDIUM',
    risk_score NUMERIC(5, 2) NOT NULL,
    decision risk_decision NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON fraud_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON fraud_alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON fraud_alerts(is_resolved) WHERE is_resolved = FALSE;
