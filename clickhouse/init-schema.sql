-- Insight Monitoring System — ClickHouse Schema
-- All tables in database: insight

-- ═══════════════════════════════════════════════════════════
-- Config Tables (ReplacingMergeTree for UPDATE/DELETE support)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id String,
    username String,
    password_hash String,
    role String DEFAULT 'admin',
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS clusters (
    id String,
    name String,
    description String DEFAULT '',
    status String DEFAULT 'active',
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS agents (
    id String,
    name String,
    agent_type String,
    agent_category String DEFAULT 'system',
    hostname String DEFAULT '',
    cluster_id String DEFAULT 'default',
    status String DEFAULT 'active',
    labels String DEFAULT '{}',
    token_id String DEFAULT '',
    agent_version String DEFAULT '',
    os_info String DEFAULT '',
    ip_address String DEFAULT '',
    last_heartbeat DateTime DEFAULT now(),
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS agent_tokens (
    id String,
    name String,
    token String,
    agent_type String DEFAULT 'any',
    cluster_id String DEFAULT 'default',
    created_by String DEFAULT '',
    last_used DateTime DEFAULT now(),
    agent_count UInt32 DEFAULT 0,
    is_active UInt8 DEFAULT 1,
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS alert_configs (
    id String,
    channel String,
    config String DEFAULT '{}',
    enabled UInt8 DEFAULT 1,
    alert_levels String DEFAULT '["critical","error"]',
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS notification_rules (
    id String,
    name String,
    metric_name String,
    operator String DEFAULT '>',
    threshold Float64,
    duration_minutes UInt32 DEFAULT 5,
    channels String DEFAULT '["telegram"]',
    enabled UInt8 DEFAULT 1,
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS webhooks (
    id String,
    name String,
    url String,
    type String DEFAULT 'custom',
    events String DEFAULT '["critical","error"]',
    enabled UInt8 DEFAULT 1,
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS settings (
    key String,
    value String,
    _version UInt64 DEFAULT toUnixTimestamp(now()),
    _deleted UInt8 DEFAULT 0,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_version)
ORDER BY key;

-- ═══════════════════════════════════════════════════════════
-- Time-Series Tables (MergeTree with TTL)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS metrics (
    id UInt64,
    agent_id String,
    metric_name String,
    metric_value Float64,
    labels String DEFAULT '{}',
    timestamp DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (agent_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS events (
    id String,
    agent_id String,
    level String,
    title String,
    message String DEFAULT '',
    source String DEFAULT '',
    namespace String DEFAULT '',
    resource String DEFAULT '',
    details String DEFAULT '{}',
    acknowledged UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(created_at)
ORDER BY (agent_id, level, created_at)
TTL created_at + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS logs (
    id UInt64,
    agent_id String,
    namespace String DEFAULT '',
    pod_name String DEFAULT '',
    container String DEFAULT '',
    log_level String DEFAULT 'error',
    message String DEFAULT '',
    timestamp DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (agent_id, log_level, timestamp)
TTL timestamp + INTERVAL 14 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS traces (
    id String,
    agent_id String,
    trace_id String DEFAULT '',
    span_name String DEFAULT '',
    service_name String DEFAULT '',
    duration_ms Float64 DEFAULT 0,
    status String DEFAULT 'ok',
    attributes String DEFAULT '{}',
    timestamp DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (agent_id, service_name, timestamp)
TTL timestamp + INTERVAL 7 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS processes (
    id UInt64,
    agent_id String,
    snapshot String DEFAULT '[]',
    timestamp DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (agent_id, timestamp)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS audit_logs (
    id UInt64,
    user_id String DEFAULT 'system',
    username String DEFAULT 'system',
    action String,
    resource String DEFAULT '',
    details String DEFAULT '{}',
    ip String DEFAULT '',
    timestamp DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (user_id, timestamp)
TTL timestamp + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS reports (
    id String,
    report_type String,
    content String DEFAULT '{}',
    generated_at DateTime DEFAULT now(),
    sent_to String DEFAULT '[]'
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(generated_at)
ORDER BY (report_type, generated_at)
SETTINGS index_granularity = 8192;

-- ═══════════════════════════════════════════════════════════
-- Default Data
-- ═══════════════════════════════════════════════════════════

INSERT INTO clusters (id, name, description, status, _version, _deleted) VALUES
    ('default', 'Default Cluster', 'Default monitoring cluster', 'active', 1, 0);
