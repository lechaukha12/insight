"""
Insight Monitoring System - Database Connection & Operations
Supports PostgreSQL (production) and SQLite (dev fallback).
Set DATABASE_URL env var:
  - postgresql://user:pass@host:5432/insight  → PostgreSQL
  - /path/to/file.db or insight.db            → SQLite
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

DATABASE_URL = os.getenv("DATABASE_URL", "insight.db")
CLICKHOUSE_URL = os.getenv("CLICKHOUSE_URL", "")  # e.g. http://clickhouse:8123

# Detect database type
IS_POSTGRES = DATABASE_URL.startswith("postgres")
IS_CLICKHOUSE = bool(CLICKHOUSE_URL)

# PostgreSQL table creation (with JSONB)
_PG_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    agent_category TEXT DEFAULT 'system',
    hostname TEXT DEFAULT '',
    cluster_id TEXT DEFAULT 'default',
    status TEXT DEFAULT 'active',
    labels JSONB DEFAULT '{}',
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metrics (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    labels JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_agent ON metrics(agent_id);
CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    source TEXT DEFAULT '',
    namespace TEXT DEFAULT '',
    resource TEXT DEFAULT '',
    details JSONB DEFAULT '{}',
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_level ON events(level);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at);

CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    namespace TEXT DEFAULT '',
    pod_name TEXT DEFAULT '',
    container TEXT DEFAULT '',
    log_level TEXT DEFAULT 'error',
    message TEXT DEFAULT '',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_agent ON logs(agent_id);
CREATE INDEX IF NOT EXISTS idx_logs_time ON logs(timestamp);

CREATE TABLE IF NOT EXISTS alert_configs (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    alert_levels JSONB DEFAULT '["critical","error"]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT '>',
    threshold DOUBLE PRECISION NOT NULL,
    duration_minutes INTEGER DEFAULT 5,
    channels JSONB DEFAULT '["telegram"]',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,
    content JSONB DEFAULT '{}',
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    sent_to JSONB DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'custom',
    events JSONB DEFAULT '["critical","error"]',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processes (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '[]',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    trace_id TEXT,
    span_name TEXT,
    service_name TEXT,
    duration_ms DOUBLE PRECISION,
    status TEXT DEFAULT 'ok',
    attributes JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT DEFAULT 'system',
    username TEXT DEFAULT 'system',
    action TEXT NOT NULL,
    resource TEXT DEFAULT '',
    details JSONB DEFAULT '{}',
    ip TEXT DEFAULT '',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);

-- Insert default cluster
INSERT INTO clusters (id, name, description) VALUES ('default', 'Default Cluster', 'Default monitoring cluster')
ON CONFLICT (id) DO NOTHING;
"""

# SQLite table creation (backward compatible)
_SQLITE_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    agent_category TEXT DEFAULT 'system',
    hostname TEXT DEFAULT '',
    cluster_id TEXT DEFAULT 'default',
    status TEXT DEFAULT 'active',
    labels TEXT DEFAULT '{}',
    last_heartbeat TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    labels TEXT DEFAULT '{}',
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_metrics_agent ON metrics(agent_id);
CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    source TEXT DEFAULT '',
    namespace TEXT DEFAULT '',
    resource TEXT DEFAULT '',
    details TEXT DEFAULT '{}',
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_level ON events(level);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    namespace TEXT DEFAULT '',
    pod_name TEXT DEFAULT '',
    container TEXT DEFAULT '',
    log_level TEXT DEFAULT 'error',
    message TEXT DEFAULT '',
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_logs_agent ON logs(agent_id);
CREATE INDEX IF NOT EXISTS idx_logs_time ON logs(timestamp);

CREATE TABLE IF NOT EXISTS alert_configs (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    alert_levels TEXT DEFAULT '["critical","error"]',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT '>',
    threshold REAL NOT NULL,
    duration_minutes INTEGER DEFAULT 5,
    channels TEXT DEFAULT '["telegram"]',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,
    content TEXT DEFAULT '{}',
    generated_at TEXT DEFAULT (datetime('now')),
    sent_to TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'custom',
    events TEXT DEFAULT '["critical","error"]',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    snapshot TEXT NOT NULL DEFAULT '[]',
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    trace_id TEXT,
    span_name TEXT,
    service_name TEXT,
    duration_ms REAL,
    status TEXT DEFAULT 'ok',
    attributes TEXT DEFAULT '{}',
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT DEFAULT 'system',
    username TEXT DEFAULT 'system',
    action TEXT NOT NULL,
    resource TEXT DEFAULT '',
    details TEXT DEFAULT '{}',
    ip TEXT DEFAULT '',
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
"""

# ─── PostgreSQL Connection ───

_pg_pool = None

def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import asyncpg
        import asyncio
        loop = asyncio.get_event_loop()
        _pg_pool = loop.run_until_complete(
            asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        )
    return _pg_pool

@contextmanager
def pg_connection():
    import asyncio
    pool = _get_pg_pool()
    loop = asyncio.get_event_loop()
    conn = loop.run_until_complete(pool.acquire())
    try:
        yield conn
    finally:
        loop.run_until_complete(pool.release(conn))

# ─── SQLite Connection ───

@contextmanager
def sqlite_connection():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ─── ClickHouse Connection ───

_ch_client = None

def _get_ch_client():
    """Get or create ClickHouse client singleton."""
    global _ch_client
    if _ch_client is None and IS_CLICKHOUSE:
        import clickhouse_connect
        from urllib.parse import urlparse
        parsed = urlparse(CLICKHOUSE_URL)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 8123
        _ch_client = clickhouse_connect.get_client(
            host=host, port=port, database='insight',
            connect_timeout=10, send_receive_timeout=30
        )
    return _ch_client


def _run_clickhouse(query, params=None, fetch=False):
    """Run a ClickHouse query."""
    client = _get_ch_client()
    if fetch:
        result = client.query(query, parameters=params or {})
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]
    else:
        client.command(query, parameters=params or {})
        return None


def _run_ch_insert(table, columns, data):
    """Batch insert into ClickHouse."""
    client = _get_ch_client()
    if data:
        # Convert string timestamps to datetime objects for ClickHouse
        ts_cols = {i for i, c in enumerate(columns) if c in ('timestamp', 'created_at')}
        if ts_cols:
            converted = []
            for row in data:
                new_row = list(row)
                for i in ts_cols:
                    v = new_row[i]
                    if isinstance(v, str):
                        try:
                            new_row[i] = datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            new_row[i] = datetime.now(timezone.utc).replace(tzinfo=None)
                converted.append(new_row)
            data = converted
        client.insert(table, data, column_names=columns)


def init_clickhouse():
    """Verify ClickHouse tables exist."""
    if not IS_CLICKHOUSE:
        return
    try:
        client = _get_ch_client()
        tables = client.command("SHOW TABLES FROM insight")
        print(f"[DB] ClickHouse connected: {tables}")
    except Exception as e:
        print(f"[DB] ClickHouse connection error: {e}")


# ─── Unified Interface ───

@contextmanager
def get_connection():
    """Get a database connection (PostgreSQL or SQLite)."""
    if IS_POSTGRES:
        with pg_connection() as conn:
            yield conn
    else:
        with sqlite_connection() as conn:
            yield conn


def _run_pg(query, params=None, fetch=False, fetchone=False):
    """Run a PostgreSQL query synchronously."""
    import asyncio
    pool = _get_pg_pool()

    async def _exec():
        async with pool.acquire() as conn:
            if fetchone:
                return await conn.fetchrow(query, *(params or []))
            elif fetch:
                return await conn.fetch(query, *(params or []))
            else:
                return await conn.execute(query, *(params or []))
    
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_exec())


def _run_sqlite(query, params=None, fetch=False, fetchone=False):
    """Run a SQLite query synchronously."""
    with sqlite_connection() as conn:
        cursor = conn.execute(query, params or [])
        if fetchone:
            row = cursor.fetchone()
            return dict(row) if row else None
        elif fetch:
            return [dict(r) for r in cursor.fetchall()]
        return None


def db_execute(query_sqlite, query_pg=None, params_sqlite=None, params_pg=None, fetch=False, fetchone=False):
    """Execute query on the appropriate database."""
    if IS_POSTGRES:
        q = query_pg or query_sqlite
        p = params_pg or params_sqlite
        result = _run_pg(q, p, fetch=fetch, fetchone=fetchone)
        if fetch and result:
            return [dict(r) for r in result]
        elif fetchone and result:
            return dict(result)
        return result
    else:
        return _run_sqlite(query_sqlite, params_sqlite, fetch=fetch, fetchone=fetchone)


def init_db():
    """Initialize database tables."""
    if IS_POSTGRES:
        import asyncio
        pool = _get_pg_pool()
        async def _init():
            async with pool.acquire() as conn:
                await conn.execute(_PG_CREATE_TABLES)
                try:
                    await conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS agent_category TEXT DEFAULT 'system'")
                except Exception:
                    pass
        asyncio.get_event_loop().run_until_complete(_init())
        print("[DB] PostgreSQL initialized successfully")
    else:
        with sqlite_connection() as conn:
            conn.executescript(_SQLITE_CREATE_TABLES)
            try:
                conn.execute("ALTER TABLE agents ADD COLUMN agent_category TEXT DEFAULT 'system'")
            except Exception:
                pass
            conn.execute(
                "INSERT OR IGNORE INTO clusters (id, name, description) VALUES (?, ?, ?)",
                ('default', 'Default Cluster', 'Default monitoring cluster')
            )
        print("[DB] SQLite initialized successfully")
    # Initialize ClickHouse for time-series data
    if IS_CLICKHOUSE:
        init_clickhouse()
        print("[DB] ClickHouse initialized for time-series data")


def _parse_json_field(value, default="{}"):
    """Parse JSON field that might be string or already parsed."""
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or default)
    except (json.JSONDecodeError, TypeError):
        return json.loads(default)


# ─── User CRUD ───

def create_user(username: str, password_hash: str, role: str = "admin") -> dict:
    user_id = str(uuid.uuid4())
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO users (id, username, password_hash, role) VALUES ($1, $2, $3, $4)",
            [user_id, username, password_hash, role]
        )
    else:
        _run_sqlite(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
            [user_id, username, password_hash, role]
        )
    return {"id": user_id, "username": username, "role": role}


def get_user_by_username(username: str) -> dict | None:
    if IS_POSTGRES:
        return db_execute(
            "", "SELECT * FROM users WHERE username = $1",
            params_pg=[username], fetchone=True
        )
    else:
        return _run_sqlite("SELECT * FROM users WHERE username = ?", [username], fetchone=True)


def get_user_by_id(user_id: str) -> dict | None:
    if IS_POSTGRES:
        return db_execute("", "SELECT * FROM users WHERE id = $1", params_pg=[user_id], fetchone=True)
    else:
        return _run_sqlite("SELECT * FROM users WHERE id = ?", [user_id], fetchone=True)


# ─── Cluster CRUD ───

def create_cluster(name: str, description: str = "") -> dict:
    cluster_id = str(uuid.uuid4())
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO clusters (id, name, description) VALUES ($1, $2, $3)",
            [cluster_id, name, description]
        )
    else:
        _run_sqlite(
            "INSERT INTO clusters (id, name, description) VALUES (?, ?, ?)",
            [cluster_id, name, description]
        )
    return {"id": cluster_id, "name": name, "description": description, "status": "active"}


def list_clusters() -> list[dict]:
    if IS_POSTGRES:
        return db_execute("", "SELECT * FROM clusters ORDER BY created_at DESC", fetch=True) or []
    else:
        return _run_sqlite("SELECT * FROM clusters ORDER BY created_at DESC", fetch=True) or []


def get_cluster(cluster_id: str) -> dict | None:
    if IS_POSTGRES:
        return db_execute("", "SELECT * FROM clusters WHERE id = $1", params_pg=[cluster_id], fetchone=True)
    else:
        return _run_sqlite("SELECT * FROM clusters WHERE id = ?", [cluster_id], fetchone=True)


# ─── Agent CRUD ───

def _resolve_category(agent_type: str, agent_category: str = None) -> str:
    """Auto-resolve agent_category from agent_type if not provided."""
    if agent_category:
        return agent_category
    app_types = {"opentelemetry"}
    return "application" if agent_type in app_types else "system"


def register_agent(name: str, agent_type: str, hostname: str = "", labels: dict = None, cluster_id: str = "default", agent_category: str = None) -> dict:
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    labels_val = json.dumps(labels or {})
    category = _resolve_category(agent_type, agent_category)
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO agents (id, name, agent_type, agent_category, hostname, cluster_id, status, labels, last_heartbeat) VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $8)",
            [agent_id, name, agent_type, category, hostname, cluster_id, labels_val, now]
        )
    else:
        _run_sqlite(
            "INSERT INTO agents (id, name, agent_type, agent_category, hostname, cluster_id, status, labels, last_heartbeat, created_at) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            [agent_id, name, agent_type, category, hostname, cluster_id, labels_val, now, now]
        )
    return {"id": agent_id, "name": name, "agent_type": agent_type, "agent_category": category, "status": "active"}


def get_agent(agent_id: str) -> dict | None:
    if IS_POSTGRES:
        row = db_execute("", "SELECT * FROM agents WHERE id = $1", params_pg=[agent_id], fetchone=True)
    else:
        row = _run_sqlite("SELECT * FROM agents WHERE id = ?", [agent_id], fetchone=True)
    if row:
        row["labels"] = _parse_json_field(row.get("labels"))
    return row


def get_or_create_agent(agent_id: str, name: str, agent_type: str, hostname: str = "", cluster_id: str = "default", agent_category: str = None) -> dict:
    agent = get_agent(agent_id)
    if agent:
        # Update category if provided and different
        if agent_category and agent.get("agent_category") != agent_category:
            if IS_POSTGRES:
                _run_pg("UPDATE agents SET agent_category=$1 WHERE id=$2", [agent_category, agent_id])
            else:
                _run_sqlite("UPDATE agents SET agent_category=? WHERE id=?", [agent_category, agent_id])
        update_agent_heartbeat(agent_id)
        return agent
    return register_agent_with_id(agent_id, name, agent_type, hostname, cluster_id=cluster_id, agent_category=agent_category)


def register_agent_with_id(agent_id: str, name: str, agent_type: str, hostname: str = "", labels: dict = None, cluster_id: str = "default", agent_category: str = None) -> dict:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    labels_val = json.dumps(labels or {})
    category = _resolve_category(agent_type, agent_category)
    if IS_POSTGRES:
        _run_pg(
            """INSERT INTO agents (id, name, agent_type, agent_category, hostname, cluster_id, status, labels, last_heartbeat)
               VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $8)
               ON CONFLICT (id) DO UPDATE SET name=$2, agent_category=$4, last_heartbeat=$8, status='active'""",
            [agent_id, name, agent_type, category, hostname, cluster_id, labels_val, now]
        )
    else:
        _run_sqlite(
            "INSERT OR REPLACE INTO agents (id, name, agent_type, agent_category, hostname, cluster_id, status, labels, last_heartbeat, created_at) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            [agent_id, name, agent_type, category, hostname, cluster_id, labels_val, now, now]
        )
    return {"id": agent_id, "name": name, "agent_type": agent_type, "agent_category": category, "status": "active"}


def list_agents(cluster_id: str = None) -> list[dict]:
    if IS_POSTGRES:
        if cluster_id and cluster_id != 'all':
            rows = db_execute("", "SELECT * FROM agents WHERE cluster_id = $1 ORDER BY created_at DESC",
                            params_pg=[cluster_id], fetch=True) or []
        else:
            rows = db_execute("", "SELECT * FROM agents ORDER BY created_at DESC", fetch=True) or []
    else:
        if cluster_id and cluster_id != 'all':
            rows = _run_sqlite("SELECT * FROM agents WHERE cluster_id = ? ORDER BY created_at DESC",
                              [cluster_id], fetch=True) or []
        else:
            rows = _run_sqlite("SELECT * FROM agents ORDER BY created_at DESC", fetch=True) or []
    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
    return rows


def update_agent_heartbeat(agent_id: str):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    if IS_POSTGRES:
        _run_pg("UPDATE agents SET last_heartbeat = $1, status = 'active' WHERE id = $2", [now, agent_id])
    else:
        _run_sqlite("UPDATE agents SET last_heartbeat = ?, status = 'active' WHERE id = ?", [now, agent_id])


def update_agent_status(agent_id: str, status: str):
    if IS_POSTGRES:
        _run_pg("UPDATE agents SET status = $1 WHERE id = $2", [status, agent_id])
    else:
        _run_sqlite("UPDATE agents SET status = ? WHERE id = ?", [status, agent_id])


# ─── Metrics CRUD ───

def insert_metrics(agent_id: str, metrics: list[dict]):
    if IS_CLICKHOUSE:
        rows = []
        for m in metrics:
            ts = m.get("timestamp", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
            rows.append([0, agent_id, m.get("metric_name", ""), m.get("metric_value", 0), json.dumps(m.get("labels", {})), ts])
        _run_ch_insert('metrics', ['id', 'agent_id', 'metric_name', 'metric_value', 'labels', 'timestamp'], rows)
        return
    for m in metrics:
        ts = m.get("timestamp", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
        labels_val = json.dumps(m.get("labels", {}))
        if IS_POSTGRES:
            _run_pg(
                "INSERT INTO metrics (agent_id, metric_name, metric_value, labels, timestamp) VALUES ($1, $2, $3, $4, $5)",
                [agent_id, m.get("metric_name", ""), m.get("metric_value", 0), labels_val, ts]
            )
        else:
            _run_sqlite(
                "INSERT INTO metrics (agent_id, metric_name, metric_value, labels, timestamp) VALUES (?, ?, ?, ?, ?)",
                [agent_id, m.get("metric_name", ""), m.get("metric_value", 0), labels_val, ts]
            )


def get_metrics(agent_id: str = None, metric_name: str = None, last_hours: int = 24, limit: int = 1000) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        query = f"SELECT * FROM metrics WHERE timestamp >= '{cutoff}'"
        if agent_id: query += f" AND agent_id = '{agent_id}'"
        if metric_name: query += f" AND metric_name = '{metric_name}'"
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        rows = _run_clickhouse(query, fetch=True) or []
    elif IS_POSTGRES:
        query = "SELECT * FROM metrics WHERE timestamp >= $1"
        params = [cutoff]; idx = 2
        if agent_id: query += f" AND agent_id = ${idx}"; params.append(agent_id); idx += 1
        if metric_name: query += f" AND metric_name = ${idx}"; params.append(metric_name); idx += 1
        query += f" ORDER BY timestamp DESC LIMIT ${idx}"; params.append(limit)
        rows = db_execute("", query, params_pg=params, fetch=True) or []
    else:
        query = "SELECT * FROM metrics WHERE timestamp >= ?"; params = [cutoff]
        if agent_id: query += " AND agent_id = ?"; params.append(agent_id)
        if metric_name: query += " AND metric_name = ?"; params.append(metric_name)
        query += " ORDER BY timestamp DESC LIMIT ?"; params.append(limit)
        rows = _run_sqlite(query, params, fetch=True) or []
    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
    return rows


def get_latest_metrics_per_agent() -> dict[str, list[dict]]:
    query = """SELECT m.* FROM metrics m
               INNER JOIN (
                   SELECT agent_id, metric_name, MAX(timestamp) as max_ts
                   FROM metrics GROUP BY agent_id, metric_name
               ) latest ON m.agent_id = latest.agent_id
                   AND m.metric_name = latest.metric_name
                   AND m.timestamp = latest.max_ts
               ORDER BY m.agent_id, m.metric_name"""
    if IS_CLICKHOUSE:
        rows = _run_clickhouse(query, fetch=True) or []
    elif IS_POSTGRES:
        rows = db_execute("", query, fetch=True) or []
    else:
        rows = _run_sqlite(query, fetch=True) or []

    result: dict[str, list[dict]] = {}
    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
        aid = r["agent_id"]
        if aid not in result:
            result[aid] = []
        result[aid].append(r)
    return result


def get_metrics_timeseries(agent_id: str = None, last_hours: int = 6, metric_names: list[str] = None) -> list[dict]:
    """Get metrics as time-series data for Recharts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        query = f"SELECT metric_name, metric_value, timestamp FROM metrics WHERE timestamp >= '{cutoff}'"
        if agent_id: query += f" AND agent_id = '{agent_id}'"
        if metric_names:
            names_str = ", ".join(f"'{n}'" for n in metric_names)
            query += f" AND metric_name IN ({names_str})"
        query += " ORDER BY timestamp ASC"
        rows = _run_clickhouse(query, fetch=True) or []
    elif IS_POSTGRES:
        query = "SELECT metric_name, metric_value, timestamp FROM metrics WHERE timestamp >= $1"
        params = [cutoff]; idx = 2
        if agent_id:
            query += f" AND agent_id = ${idx}"; params.append(agent_id); idx += 1
        if metric_names:
            placeholders = ", ".join(f"${idx + i}" for i in range(len(metric_names)))
            query += f" AND metric_name IN ({placeholders})"
            params.extend(metric_names)
        query += " ORDER BY timestamp ASC"
        rows = db_execute("", query, params_pg=params, fetch=True) or []
    else:
        query = "SELECT metric_name, metric_value, timestamp FROM metrics WHERE timestamp >= ?"
        params: list[Any] = [cutoff]
        if agent_id: query += " AND agent_id = ?"; params.append(agent_id)
        if metric_names:
            placeholders = ",".join("?" * len(metric_names))
            query += f" AND metric_name IN ({placeholders})"
            params.extend(metric_names)
        query += " ORDER BY timestamp ASC"
        rows = _run_sqlite(query, params, fetch=True) or []

    time_map: dict[str, dict] = {}
    for r in rows:
        ts = str(r["timestamp"])[:16]
        if ts not in time_map:
            time_map[ts] = {"time": ts}
        time_map[ts][r["metric_name"]] = round(float(r["metric_value"]), 2)
    return list(time_map.values())


def get_event_counts_by_hour(last_hours: int = 24) -> list[dict]:
    """Get event counts grouped by hour and level."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        query = f"""SELECT formatDateTime(created_at, '%Y-%m-%d %H:00') as hour,
                          level, count() as count
                   FROM events WHERE created_at >= '{cutoff}'
                   GROUP BY hour, level ORDER BY hour ASC"""
        rows = _run_clickhouse(query, fetch=True) or []
    elif IS_POSTGRES:
        query = """SELECT to_char(created_at, 'YYYY-MM-DD HH24:00') as hour,
                          level, COUNT(*) as count
                   FROM events WHERE created_at >= $1
                   GROUP BY hour, level ORDER BY hour ASC"""
        rows = db_execute("", query, params_pg=[cutoff], fetch=True) or []
    else:
        query = """SELECT strftime('%Y-%m-%d %H:00', created_at) as hour,
                          level, COUNT(*) as count
                   FROM events WHERE created_at >= ?
                   GROUP BY hour, level ORDER BY hour ASC"""
        rows = _run_sqlite(query, [cutoff], fetch=True) or []

    hour_map: dict[str, dict] = {}
    for r in rows:
        h = r["hour"]
        if h not in hour_map:
            hour_map[h] = {"hour": h, "critical": 0, "error": 0, "warning": 0, "info": 0}
        hour_map[h][r["level"]] = r["count"]
    return list(hour_map.values())


# ─── Events CRUD ───

def insert_events(agent_id: str, events: list[dict]):
    if IS_CLICKHOUSE:
        rows = []
        for e in events:
            event_id = str(uuid.uuid4())
            ts = e.get("timestamp", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
            rows.append([event_id, agent_id, e.get("level","info"), e.get("title",""), e.get("message",""),
                         e.get("source",""), e.get("namespace",""), e.get("resource",""), json.dumps(e.get("details", {})), 0, ts])
        _run_ch_insert('events', ['id','agent_id','level','title','message','source','namespace','resource','details','acknowledged','created_at'], rows)
        return
    for e in events:
        event_id = str(uuid.uuid4())
        ts = e.get("timestamp", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
        details_val = json.dumps(e.get("details", {}))
        if IS_POSTGRES:
            _run_pg(
                "INSERT INTO events (id, agent_id, level, title, message, source, namespace, resource, details, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                [event_id, agent_id, e.get("level","info"), e.get("title",""), e.get("message",""),
                 e.get("source",""), e.get("namespace",""), e.get("resource",""), details_val, ts]
            )
        else:
            _run_sqlite(
                "INSERT INTO events (id, agent_id, level, title, message, source, namespace, resource, details, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [event_id, agent_id, e.get("level","info"), e.get("title",""), e.get("message",""),
                 e.get("source",""), e.get("namespace",""), e.get("resource",""), details_val, ts]
            )


def get_events(agent_id: str = None, level: str = None, last_hours: int = 24, limit: int = 200) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        query = f"SELECT * FROM events WHERE created_at >= '{cutoff}'"
        if agent_id: query += f" AND agent_id = '{agent_id}'"
        if level: query += f" AND level = '{level}'"
        query += f" ORDER BY created_at DESC LIMIT {limit}"
        rows = _run_clickhouse(query, fetch=True) or []
    elif IS_POSTGRES:
        query = "SELECT * FROM events WHERE created_at >= $1"
        params = [cutoff]; idx = 2
        if agent_id: query += f" AND agent_id = ${idx}"; params.append(agent_id); idx += 1
        if level: query += f" AND level = ${idx}"; params.append(level); idx += 1
        query += f" ORDER BY created_at DESC LIMIT ${idx}"; params.append(limit)
        rows = db_execute("", query, params_pg=params, fetch=True) or []
    else:
        query = "SELECT * FROM events WHERE created_at >= ?"; params = [cutoff]
        if agent_id: query += " AND agent_id = ?"; params.append(agent_id)
        if level: query += " AND level = ?"; params.append(level)
        query += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = _run_sqlite(query, params, fetch=True) or []
    for r in rows:
        r["details"] = _parse_json_field(r.get("details"))
    return rows


def get_event_counts(last_hours: int = 24) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        rows = _run_clickhouse(f"SELECT level, count() as cnt FROM events WHERE created_at >= '{cutoff}' GROUP BY level", fetch=True) or []
    elif IS_POSTGRES:
        rows = db_execute("", "SELECT level, COUNT(*) as cnt FROM events WHERE created_at >= $1 GROUP BY level",
                         params_pg=[cutoff], fetch=True) or []
    else:
        rows = _run_sqlite("SELECT level, COUNT(*) as cnt FROM events WHERE created_at >= ? GROUP BY level",
                          [cutoff], fetch=True) or []
    return {r["level"]: r["cnt"] for r in rows}


def acknowledge_event(event_id: str):
    if IS_POSTGRES:
        _run_pg("UPDATE events SET acknowledged = TRUE WHERE id = $1", [event_id])
    else:
        _run_sqlite("UPDATE events SET acknowledged = 1 WHERE id = ?", [event_id])


# ─── Logs CRUD ───

def insert_logs(agent_id: str, logs: list[dict]):
    if IS_CLICKHOUSE:
        rows = []
        for log in logs:
            ts = log.get("timestamp", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
            rows.append([0, agent_id, log.get("namespace",""), log.get("pod_name",""), log.get("container",""),
                         log.get("log_level","error"), log.get("message",""), ts])
        _run_ch_insert('logs', ['id','agent_id','namespace','pod_name','container','log_level','message','timestamp'], rows)
        return
    for log in logs:
        ts = log.get("timestamp", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
        if IS_POSTGRES:
            _run_pg(
                "INSERT INTO logs (agent_id, namespace, pod_name, container, log_level, message, timestamp) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                [agent_id, log.get("namespace",""), log.get("pod_name",""), log.get("container",""),
                 log.get("log_level","error"), log.get("message",""), ts]
            )
        else:
            _run_sqlite(
                "INSERT INTO logs (agent_id, namespace, pod_name, container, log_level, message, timestamp) VALUES (?,?,?,?,?,?,?)",
                [agent_id, log.get("namespace",""), log.get("pod_name",""), log.get("container",""),
                 log.get("log_level","error"), log.get("message",""), ts]
            )


def get_logs(agent_id: str = None, last_hours: int = 24, limit: int = 500) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        query = f"SELECT * FROM logs WHERE timestamp >= '{cutoff}'"
        if agent_id: query += f" AND agent_id = '{agent_id}'"
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        return _run_clickhouse(query, fetch=True) or []
    elif IS_POSTGRES:
        query = "SELECT * FROM logs WHERE timestamp >= $1"; params = [cutoff]; idx = 2
        if agent_id: query += f" AND agent_id = ${idx}"; params.append(agent_id); idx += 1
        query += f" ORDER BY timestamp DESC LIMIT ${idx}"; params.append(limit)
        return db_execute("", query, params_pg=params, fetch=True) or []
    else:
        query = "SELECT * FROM logs WHERE timestamp >= ?"; params = [cutoff]
        if agent_id: query += " AND agent_id = ?"; params.append(agent_id)
        query += " ORDER BY timestamp DESC LIMIT ?"; params.append(limit)
        return _run_sqlite(query, params, fetch=True) or []


# ─── Alert Config CRUD ───

def save_alert_config(channel: str, config: dict, enabled: bool = True, alert_levels: list[str] = None) -> dict:
    config_id = str(uuid.uuid4())
    config_val = json.dumps(config)
    levels_val = json.dumps(alert_levels or ["critical", "error"])
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO alert_configs (id, channel, config, enabled, alert_levels) VALUES ($1,$2,$3,$4,$5)",
            [config_id, channel, config_val, enabled, levels_val]
        )
    else:
        _run_sqlite(
            "INSERT INTO alert_configs (id, channel, config, enabled, alert_levels) VALUES (?,?,?,?,?)",
            [config_id, channel, config_val, 1 if enabled else 0, levels_val]
        )
    return {"id": config_id, "channel": channel, "enabled": enabled}


def get_alert_configs(channel: str = None) -> list[dict]:
    if IS_POSTGRES:
        if channel:
            rows = db_execute("", "SELECT * FROM alert_configs WHERE channel = $1", params_pg=[channel], fetch=True) or []
        else:
            rows = db_execute("", "SELECT * FROM alert_configs", fetch=True) or []
    else:
        if channel:
            rows = _run_sqlite("SELECT * FROM alert_configs WHERE channel = ?", [channel], fetch=True) or []
        else:
            rows = _run_sqlite("SELECT * FROM alert_configs", fetch=True) or []
    for r in rows:
        r["config"] = _parse_json_field(r.get("config"))
        r["alert_levels"] = _parse_json_field(r.get("alert_levels"), "[]")
        r["enabled"] = bool(r.get("enabled", 0))
    return rows


def delete_alert_config(config_id: str):
    if IS_POSTGRES:
        _run_pg("DELETE FROM alert_configs WHERE id = $1", [config_id])
    else:
        _run_sqlite("DELETE FROM alert_configs WHERE id = ?", [config_id])


# ─── Notification Rules CRUD ───

def save_rule(name: str, metric_name: str, operator: str, threshold: float, duration_minutes: int = 5, channels: list[str] = None) -> dict:
    rule_id = str(uuid.uuid4())
    channels_val = json.dumps(channels or ["telegram"])
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO notification_rules (id, name, metric_name, operator, threshold, duration_minutes, channels) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            [rule_id, name, metric_name, operator, threshold, duration_minutes, channels_val]
        )
    else:
        _run_sqlite(
            "INSERT INTO notification_rules (id, name, metric_name, operator, threshold, duration_minutes, channels) VALUES (?,?,?,?,?,?,?)",
            [rule_id, name, metric_name, operator, threshold, duration_minutes, channels_val]
        )
    return {"id": rule_id, "name": name, "metric_name": metric_name, "operator": operator, "threshold": threshold}


def get_rules(enabled_only: bool = False) -> list[dict]:
    if IS_POSTGRES:
        q = "SELECT * FROM notification_rules"
        if enabled_only:
            q += " WHERE enabled = TRUE"
        q += " ORDER BY created_at DESC"
        rows = db_execute("", q, fetch=True) or []
    else:
        q = "SELECT * FROM notification_rules"
        if enabled_only:
            q += " WHERE enabled = 1"
        q += " ORDER BY created_at DESC"
        rows = _run_sqlite(q, fetch=True) or []
    for r in rows:
        r["channels"] = _parse_json_field(r.get("channels"), "[]")
        r["enabled"] = bool(r.get("enabled", 0))
    return rows


def delete_rule(rule_id: str):
    if IS_POSTGRES:
        _run_pg("DELETE FROM notification_rules WHERE id = $1", [rule_id])
    else:
        _run_sqlite("DELETE FROM notification_rules WHERE id = ?", [rule_id])


def toggle_rule(rule_id: str, enabled: bool):
    if IS_POSTGRES:
        _run_pg("UPDATE notification_rules SET enabled = $1 WHERE id = $2", [enabled, rule_id])
    else:
        _run_sqlite("UPDATE notification_rules SET enabled = ? WHERE id = ?", [1 if enabled else 0, rule_id])


# ─── Reports CRUD ───

def save_report(report_type: str, content: dict, sent_to: list[str] = None) -> dict:
    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    content_val = json.dumps(content)
    sent_val = json.dumps(sent_to or [])
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO reports (id, report_type, content, generated_at, sent_to) VALUES ($1,$2,$3,$4,$5)",
            [report_id, report_type, content_val, now, sent_val]
        )
    else:
        _run_sqlite(
            "INSERT INTO reports (id, report_type, content, generated_at, sent_to) VALUES (?,?,?,?,?)",
            [report_id, report_type, content_val, now, sent_val]
        )
    return {"id": report_id, "report_type": report_type, "generated_at": now}


def get_reports(limit: int = 20) -> list[dict]:
    if IS_POSTGRES:
        rows = db_execute("", "SELECT * FROM reports ORDER BY generated_at DESC LIMIT $1",
                         params_pg=[limit], fetch=True) or []
    else:
        rows = _run_sqlite("SELECT * FROM reports ORDER BY generated_at DESC LIMIT ?", [limit], fetch=True) or []
    for r in rows:
        r["content"] = _parse_json_field(r.get("content"))
        r["sent_to"] = _parse_json_field(r.get("sent_to"), "[]")
    return rows


# ─── Settings CRUD ───

def get_setting(key: str, default: Any = None) -> Any:
    if IS_POSTGRES:
        row = db_execute("", "SELECT value FROM settings WHERE key = $1", params_pg=[key], fetchone=True)
    else:
        row = _run_sqlite("SELECT value FROM settings WHERE key = ?", [key], fetchone=True)
    if row:
        return _parse_json_field(row["value"])
    return default


def set_setting(key: str, value: Any):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    serialized = json.dumps(value) if not isinstance(value, str) else value
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, $3) ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = $3",
            [key, serialized, now]
        )
    else:
        _run_sqlite(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            [key, serialized, now]
        )


# ─── Audit Log CRUD ───

def insert_audit_log(user_id: str = "system", username: str = "system", action: str = "", resource: str = "", details: dict = None, ip: str = ""):
    details_val = json.dumps(details or {})
    if IS_CLICKHOUSE:
        _run_ch_insert('audit_logs', ['id','user_id','username','action','resource','details','ip','timestamp'],
                       [[0, user_id, username, action, resource, details_val, ip, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')]])
    elif IS_POSTGRES:
        _run_pg(
            "INSERT INTO audit_logs (user_id, username, action, resource, details, ip) VALUES ($1,$2,$3,$4,$5,$6)",
            [user_id, username, action, resource, details_val, ip]
        )
    else:
        _run_sqlite(
            "INSERT INTO audit_logs (user_id, username, action, resource, details, ip) VALUES (?,?,?,?,?,?)",
            [user_id, username, action, resource, details_val, ip]
        )


def get_audit_logs(last_hours: int = 168, limit: int = 100) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        rows = _run_clickhouse(f"SELECT * FROM audit_logs WHERE timestamp >= '{cutoff}' ORDER BY timestamp DESC LIMIT {limit}", fetch=True) or []
    elif IS_POSTGRES:
        rows = db_execute("", "SELECT * FROM audit_logs WHERE timestamp >= $1 ORDER BY timestamp DESC LIMIT $2",
                         params_pg=[cutoff, limit], fetch=True) or []
    else:
        rows = _run_sqlite("SELECT * FROM audit_logs WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                          [cutoff, limit], fetch=True) or []
    for r in rows:
        r["details"] = _parse_json_field(r.get("details"))
    return rows


# ─── User Management ───

def list_users() -> list[dict]:
    if IS_POSTGRES:
        rows = db_execute("", "SELECT id, username, role, created_at FROM users ORDER BY created_at DESC", fetch=True) or []
    else:
        rows = _run_sqlite("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC", fetch=True) or []
    return rows


def update_user_password(user_id: str, new_password_hash: str):
    if IS_POSTGRES:
        _run_pg("UPDATE users SET password_hash = $1 WHERE id = $2", [new_password_hash, user_id])
    else:
        _run_sqlite("UPDATE users SET password_hash = ? WHERE id = ?", [new_password_hash, user_id])


def delete_user(user_id: str):
    if IS_POSTGRES:
        _run_pg("DELETE FROM users WHERE id = $1", [user_id])
    else:
        _run_sqlite("DELETE FROM users WHERE id = ?", [user_id])


# ─── Webhooks CRUD ───

def save_webhook(name: str, url: str, wh_type: str = "custom", events: list[str] = None) -> dict:
    wh_id = str(uuid.uuid4())
    events_val = json.dumps(events or ["critical", "error"])
    if IS_POSTGRES:
        _run_pg(
            "INSERT INTO webhooks (id, name, url, type, events) VALUES ($1,$2,$3,$4,$5)",
            [wh_id, name, url, wh_type, events_val]
        )
    else:
        _run_sqlite(
            "INSERT INTO webhooks (id, name, url, type, events) VALUES (?,?,?,?,?)",
            [wh_id, name, url, wh_type, events_val]
        )
    return {"id": wh_id, "name": name, "url": url, "type": wh_type}


def get_webhooks(enabled_only: bool = False) -> list[dict]:
    if IS_POSTGRES:
        q = "SELECT * FROM webhooks"
        if enabled_only: q += " WHERE enabled = TRUE"
        rows = db_execute("", q, fetch=True) or []
    else:
        q = "SELECT * FROM webhooks"
        if enabled_only: q += " WHERE enabled = 1"
        rows = _run_sqlite(q, fetch=True) or []
    for r in rows:
        r["events"] = _parse_json_field(r.get("events"), "[]")
        r["enabled"] = bool(r.get("enabled", 0))
    return rows


def delete_webhook(wh_id: str):
    if IS_POSTGRES:
        _run_pg("DELETE FROM webhooks WHERE id = $1", [wh_id])
    else:
        _run_sqlite("DELETE FROM webhooks WHERE id = ?", [wh_id])


def toggle_webhook(wh_id: str, enabled: bool):
    if IS_POSTGRES:
        _run_pg("UPDATE webhooks SET enabled = $1 WHERE id = $2", [enabled, wh_id])
    else:
        _run_sqlite("UPDATE webhooks SET enabled = ? WHERE id = ?", [1 if enabled else 0, wh_id])


# ─── Process Snapshots ───

def save_process_snapshot(agent_id: str, processes: list[dict]):
    """Save latest process snapshot for an agent (replace old one)."""
    snapshot_val = json.dumps(processes)
    if IS_CLICKHOUSE:
        _run_clickhouse(f"ALTER TABLE processes DELETE WHERE agent_id = '{agent_id}'")
        _run_ch_insert('processes', ['id', 'agent_id', 'snapshot', 'timestamp'],
                       [[0, agent_id, snapshot_val, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')]])
    elif IS_POSTGRES:
        _run_pg("DELETE FROM processes WHERE agent_id = $1", [agent_id])
        _run_pg("INSERT INTO processes (agent_id, snapshot) VALUES ($1, $2)", [agent_id, snapshot_val])
    else:
        _run_sqlite("DELETE FROM processes WHERE agent_id = ?", [agent_id])
        _run_sqlite("INSERT INTO processes (agent_id, snapshot) VALUES (?, ?)", [agent_id, snapshot_val])


def get_process_snapshot(agent_id: str) -> list[dict]:
    """Get latest process snapshot for an agent."""
    if IS_CLICKHOUSE:
        rows = _run_clickhouse(f"SELECT snapshot, timestamp FROM processes WHERE agent_id = '{agent_id}' ORDER BY timestamp DESC LIMIT 1", fetch=True) or []
    elif IS_POSTGRES:
        rows = db_execute("", "SELECT snapshot, timestamp FROM processes WHERE agent_id = $1 ORDER BY timestamp DESC LIMIT 1",
                         params_pg=[agent_id], fetch=True) or []
    else:
        rows = _run_sqlite("SELECT snapshot, timestamp FROM processes WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 1",
                          [agent_id], fetch=True) or []
    if rows:
        return {"processes": _parse_json_field(rows[0].get("snapshot"), "[]"), "timestamp": rows[0].get("timestamp")}
    return {"processes": [], "timestamp": None}


# ─── Traces ───

def insert_traces(agent_id: str, traces: list[dict]):
    """Insert OTLP trace spans."""
    if IS_CLICKHOUSE:
        rows = []
        for t in traces:
            trace_id = t.get("trace_id", str(uuid.uuid4()))
            span_id = t.get("span_id", str(uuid.uuid4()))
            rows.append([span_id, agent_id, trace_id, t.get("span_name",""), t.get("service_name",""),
                         t.get("duration_ms",0), t.get("status","ok"), json.dumps(t.get("attributes", {})),
                         datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')])
        _run_ch_insert('traces', ['id','agent_id','trace_id','span_name','service_name','duration_ms','status','attributes','timestamp'], rows)
        return
    for t in traces:
        trace_id = t.get("trace_id", str(uuid.uuid4()))
        span_id = t.get("span_id", str(uuid.uuid4()))
        attrs_val = json.dumps(t.get("attributes", {}))
        if IS_POSTGRES:
            _run_pg(
                "INSERT INTO traces (id, agent_id, trace_id, span_name, service_name, duration_ms, status, attributes) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                [span_id, agent_id, trace_id, t.get("span_name",""), t.get("service_name",""),
                 t.get("duration_ms",0), t.get("status","ok"), attrs_val]
            )
        else:
            _run_sqlite(
                "INSERT INTO traces (id, agent_id, trace_id, span_name, service_name, duration_ms, status, attributes) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [span_id, agent_id, trace_id, t.get("span_name",""), t.get("service_name",""),
                 t.get("duration_ms",0), t.get("status","ok"), attrs_val]
            )


def get_traces(agent_id: str = None, last_hours: int = 24, limit: int = 100) -> list[dict]:
    """Query traces."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        query = f"SELECT * FROM traces WHERE timestamp >= '{cutoff}'"
        if agent_id: query += f" AND agent_id = '{agent_id}'"
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        rows = _run_clickhouse(query, fetch=True) or []
    elif IS_POSTGRES:
        if agent_id:
            rows = db_execute("", "SELECT * FROM traces WHERE agent_id = $1 AND timestamp >= $2 ORDER BY timestamp DESC LIMIT $3",
                             params_pg=[agent_id, cutoff, limit], fetch=True) or []
        else:
            rows = db_execute("", "SELECT * FROM traces WHERE timestamp >= $1 ORDER BY timestamp DESC LIMIT $2",
                             params_pg=[cutoff, limit], fetch=True) or []
    else:
        if agent_id:
            rows = _run_sqlite("SELECT * FROM traces WHERE agent_id = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                              [agent_id, cutoff, limit], fetch=True) or []
        else:
            rows = _run_sqlite("SELECT * FROM traces WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                              [cutoff, limit], fetch=True) or []
    for r in rows:
        r["attributes"] = _parse_json_field(r.get("attributes"))
    return rows


def get_trace_summary(last_hours: int = 1) -> dict:
    """Get aggregate trace statistics for the Application Monitoring dashboard."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    if IS_CLICKHOUSE:
        rows = _run_clickhouse(f"""
            SELECT service_name,
                   count() as req_count,
                   avg(duration_ms) as avg_latency,
                   max(duration_ms) as max_latency,
                   quantile(0.95)(duration_ms) as p95_latency,
                   countIf(status = 'error') as error_count
            FROM traces WHERE timestamp >= '{cutoff}'
            GROUP BY service_name ORDER BY req_count DESC
        """, fetch=True) or []
    elif IS_POSTGRES:
        rows = db_execute("", """
            SELECT service_name,
                   COUNT(*) as req_count,
                   AVG(duration_ms) as avg_latency,
                   MAX(duration_ms) as max_latency,
                   PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_latency,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
            FROM traces WHERE timestamp >= $1
            GROUP BY service_name ORDER BY req_count DESC
        """, params_pg=[cutoff], fetch=True) or []
    else:
        rows = _run_sqlite("""
            SELECT service_name,
                   COUNT(*) as req_count,
                   AVG(duration_ms) as avg_latency,
                   MAX(duration_ms) as max_latency,
                   duration_ms as p95_latency,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
            FROM traces WHERE timestamp >= ?
            GROUP BY service_name ORDER BY req_count DESC
        """, [cutoff], fetch=True) or []

    total = sum(r.get("req_count", 0) for r in rows)
    total_errors = sum(r.get("error_count", 0) for r in rows)
    all_latencies = [r.get("avg_latency", 0) for r in rows if r.get("avg_latency")]
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0

    return {
        "total_requests": total,
        "avg_latency_ms": round(avg_latency, 2),
        "error_count": total_errors,
        "error_rate": round(total_errors / total * 100, 2) if total > 0 else 0,
        "services": [{
            "name": r.get("service_name", "unknown"),
            "requests": r.get("req_count", 0),
            "avg_latency_ms": round(r.get("avg_latency", 0), 2),
            "max_latency_ms": round(r.get("max_latency", 0), 2),
            "p95_latency_ms": round(r.get("p95_latency", 0), 2),
            "error_count": r.get("error_count", 0),
            "error_rate": round(r.get("error_count", 0) / r.get("req_count", 1) * 100, 2),
        } for r in rows],
        "last_hours": last_hours,
    }


# ─── Storage Stats & Retention ───

def get_storage_stats() -> dict:
    """Get storage statistics for each ClickHouse table."""
    if not IS_CLICKHOUSE:
        return {"engine": "sqlite", "tables": [], "message": "Storage stats only available with ClickHouse"}
    try:
        rows = _run_clickhouse("""
            SELECT table, formatReadableSize(sum(bytes_on_disk)) as size,
                   sum(rows) as row_count,
                   min(min_date) as oldest_data, max(max_date) as newest_data
            FROM system.parts
            WHERE database = 'insight' AND active = 1
            GROUP BY table ORDER BY sum(bytes_on_disk) DESC
        """, fetch=True) or []
        # Get TTL info
        ttl_rows = _run_clickhouse("""
            SELECT name as table, engine,
                   create_table_query
            FROM system.tables WHERE database = 'insight'
        """, fetch=True) or []
        ttl_map = {}
        for t in ttl_rows:
            q = str(t.get("create_table_query", ""))
            import re
            m = re.search(r'TTL\s+\w+\s*\+\s*(?:toIntervalDay\((\d+)\)|INTERVAL\s+(\d+)\s+DAY)', q, re.IGNORECASE)
            if m:
                ttl_map[t["table"]] = int(m.group(1) or m.group(2))
        tables = []
        for r in rows:
            tables.append({
                "name": r["table"],
                "size": r["size"],
                "rows": r["row_count"],
                "oldest": str(r.get("oldest_data", "")),
                "newest": str(r.get("newest_data", "")),
                "retention_days": ttl_map.get(r["table"], None),
            })
        return {"engine": "clickhouse", "tables": tables}
    except Exception as e:
        return {"engine": "clickhouse", "tables": [], "error": str(e)}


def apply_retention_policies() -> dict:
    """Apply retention policies from settings to ClickHouse TTL."""
    if not IS_CLICKHOUSE:
        return {"status": "skipped", "message": "Retention only available with ClickHouse"}
    # Read retention settings from SQLite/PG settings table
    retention = {
        "traces": get_setting("retention_traces_days", 7),
        "logs": get_setting("retention_logs_days", 14),
        "metrics": get_setting("retention_metrics_days", 30),
        "events": get_setting("retention_events_days", 30),
        "processes": get_setting("retention_processes_days", 3),
        "audit_logs": get_setting("retention_audit_days", 90),
    }
    ts_column = {
        "traces": "timestamp", "logs": "timestamp", "metrics": "timestamp",
        "events": "created_at", "processes": "timestamp", "audit_logs": "timestamp",
    }
    results = {}
    for table, days in retention.items():
        try:
            col = ts_column[table]
            _run_clickhouse(f"ALTER TABLE {table} MODIFY TTL {col} + INTERVAL {days} DAY DELETE")
            results[table] = {"days": days, "status": "applied"}
        except Exception as e:
            results[table] = {"days": days, "status": "error", "error": str(e)}
    return {"status": "ok", "retention": results}


def purge_all_data() -> dict:
    """Truncate all time-series tables (metrics, logs, traces, events)."""
    tables = ["metrics", "logs", "traces", "events"]
    results = {}
    for table in tables:
        try:
            if IS_CLICKHOUSE:
                _run_clickhouse(f"TRUNCATE TABLE {table}")
            elif IS_POSTGRES:
                _run_pg(f"DELETE FROM {table}")
            else:
                _run_sqlite(f"DELETE FROM {table}")
            results[table] = "purged"
        except Exception as e:
            results[table] = f"error: {e}"
    return {"status": "ok", "tables": results}

