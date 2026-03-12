-- ClickHouse Schema for Insight Monitoring System
-- Engine: MergeTree with partition by day + TTL

-- Metrics (CPU, Memory, Disk, OTel application metrics)
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

-- Events (K8s events, alerts)
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

-- Logs (application logs, OTel logs)
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

-- Traces (OTLP spans)
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

-- Processes (process snapshots)
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

-- Audit Logs
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
