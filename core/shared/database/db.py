"""
Insight Monitoring System - Database Connection & Operations
ClickHouse-only backend (v5.1.1)
Set CLICKHOUSE_URL env var: http://clickhouse:8123
"""

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, date, timedelta, timezone
from typing import Any

CLICKHOUSE_URL = os.getenv("CLICKHOUSE_URL", "http://localhost:8123")

# ─── ClickHouse Connection ───

_ch_client = None


def _get_ch_client():
    """Get or create ClickHouse client singleton with reconnect support."""
    global _ch_client
    if _ch_client is not None:
        # Verify connection is alive
        try:
            _ch_client.command("SELECT 1")
            return _ch_client
        except Exception:
            print("[DB] ClickHouse connection lost, reconnecting...", flush=True)
            _ch_client = None
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


def _run(query, params=None, fetch=False):
    """Run a ClickHouse query with auto-reconnect on failure."""
    for attempt in range(2):
        try:
            client = _get_ch_client()
            if fetch:
                result = client.query(query, parameters=params or {})
                columns = result.column_names
                return [dict(zip(columns, row)) for row in result.result_rows]
            else:
                client.command(query, parameters=params or {})
                return None
        except Exception as e:
            if attempt == 0:
                global _ch_client
                _ch_client = None  # Force reconnect on next attempt
                print(f"[DB] Query failed, retrying: {e}", flush=True)
                continue
            raise


def _insert(table, columns, data):
    """Batch insert into ClickHouse."""
    client = _get_ch_client()
    if data:
        ts_cols = {i for i, c in enumerate(columns) if c in ('timestamp', 'created_at', 'updated_at', 'last_heartbeat', 'last_used', 'generated_at')}
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
                            print(f"[DB] WARNING: Invalid timestamp format '{v}' in column '{columns[i]}', using current time", flush=True)
                            new_row[i] = datetime.now(timezone.utc).replace(tzinfo=None)
                    elif v is None:
                        new_row[i] = datetime.now(timezone.utc).replace(tzinfo=None)
                converted.append(new_row)
            data = converted
        client.insert(table, data, column_names=columns)


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _version():
    """Generate a version number for ReplacingMergeTree."""
    import time
    return int(time.time() * 1000)


def init_db():
    """Initialize ClickHouse tables. Creates all tables if they don't exist."""
    try:
        client = _get_ch_client()

        # Config tables (ReplacingMergeTree)
        _config_tables = [
            """CREATE TABLE IF NOT EXISTS users (
                id String, username String, password_hash String, role String DEFAULT 'admin',
                _version UInt64 DEFAULT toUnixTimestamp(now()), _deleted UInt8 DEFAULT 0,
                created_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY id""",

            """CREATE TABLE IF NOT EXISTS clusters (
                id String, name String, description String DEFAULT '', status String DEFAULT 'active',
                _version UInt64 DEFAULT toUnixTimestamp(now()), _deleted UInt8 DEFAULT 0,
                created_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY id""",

            """CREATE TABLE IF NOT EXISTS agents (
                id String, name String, agent_type String, agent_category String DEFAULT 'system',
                hostname String DEFAULT '', cluster_id String DEFAULT 'default', status String DEFAULT 'active',
                labels String DEFAULT '{}', token_id String DEFAULT '', agent_version String DEFAULT '',
                os_info String DEFAULT '', ip_address String DEFAULT '', last_heartbeat DateTime DEFAULT now(),
                _version UInt64 DEFAULT toUnixTimestamp(now()), _deleted UInt8 DEFAULT 0,
                created_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY id""",

            """CREATE TABLE IF NOT EXISTS agent_tokens (
                id String, name String, token String, agent_type String DEFAULT 'any',
                cluster_id String DEFAULT 'default', created_by String DEFAULT '',
                last_used DateTime DEFAULT now(), agent_count UInt32 DEFAULT 0, is_active UInt8 DEFAULT 1,
                _version UInt64 DEFAULT toUnixTimestamp(now()), _deleted UInt8 DEFAULT 0,
                created_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY id""",

            """CREATE TABLE IF NOT EXISTS alert_configs (
                id String, channel String, config String DEFAULT '{}', enabled UInt8 DEFAULT 1,
                alert_levels String DEFAULT '["critical","error"]',
                _version UInt64 DEFAULT toUnixTimestamp(now()), _deleted UInt8 DEFAULT 0,
                created_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY id""",

            """CREATE TABLE IF NOT EXISTS notification_rules (
                id String, name String, metric_name String, operator String DEFAULT '>',
                threshold Float64, duration_minutes UInt32 DEFAULT 5, channels String DEFAULT '["telegram"]',
                enabled UInt8 DEFAULT 1, _version UInt64 DEFAULT toUnixTimestamp(now()),
                _deleted UInt8 DEFAULT 0, created_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY id""",

            """CREATE TABLE IF NOT EXISTS webhooks (
                id String, name String, url String, type String DEFAULT 'custom',
                events String DEFAULT '["critical","error"]', enabled UInt8 DEFAULT 1,
                _version UInt64 DEFAULT toUnixTimestamp(now()), _deleted UInt8 DEFAULT 0,
                created_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY id""",

            """CREATE TABLE IF NOT EXISTS settings (
                key String, value String,
                _version UInt64 DEFAULT toUnixTimestamp(now()), _deleted UInt8 DEFAULT 0,
                updated_at DateTime DEFAULT now()
            ) ENGINE = ReplacingMergeTree(_version) ORDER BY key""",
        ]

        # Time-series tables (MergeTree)
        _ts_tables = [
            """CREATE TABLE IF NOT EXISTS metrics (
                id UInt64, agent_id String, metric_name String, metric_value Float64,
                labels String DEFAULT '{}', timestamp DateTime DEFAULT now()
            ) ENGINE = MergeTree() PARTITION BY toYYYYMMDD(timestamp)
            ORDER BY (agent_id, metric_name, timestamp) TTL timestamp + INTERVAL 30 DAY DELETE""",

            """CREATE TABLE IF NOT EXISTS events (
                id String, agent_id String, level String, title String, message String DEFAULT '',
                source String DEFAULT '', namespace String DEFAULT '', resource String DEFAULT '',
                details String DEFAULT '{}', acknowledged UInt8 DEFAULT 0, created_at DateTime DEFAULT now()
            ) ENGINE = MergeTree() PARTITION BY toYYYYMMDD(created_at)
            ORDER BY (agent_id, level, created_at) TTL created_at + INTERVAL 30 DAY DELETE""",

            """CREATE TABLE IF NOT EXISTS logs (
                id UInt64, agent_id String, namespace String DEFAULT '', pod_name String DEFAULT '',
                container String DEFAULT '', log_level String DEFAULT 'error', message String DEFAULT '',
                timestamp DateTime DEFAULT now()
            ) ENGINE = MergeTree() PARTITION BY toYYYYMMDD(timestamp)
            ORDER BY (agent_id, log_level, timestamp) TTL timestamp + INTERVAL 14 DAY DELETE""",

            """CREATE TABLE IF NOT EXISTS traces (
                id String, agent_id String, trace_id String DEFAULT '', span_name String DEFAULT '',
                service_name String DEFAULT '', duration_ms Float64 DEFAULT 0, status String DEFAULT 'ok',
                attributes String DEFAULT '{}', timestamp DateTime DEFAULT now()
            ) ENGINE = MergeTree() PARTITION BY toYYYYMMDD(timestamp)
            ORDER BY (agent_id, service_name, timestamp) TTL timestamp + INTERVAL 7 DAY DELETE""",

            """CREATE TABLE IF NOT EXISTS processes (
                id UInt64, agent_id String, snapshot String DEFAULT '[]', timestamp DateTime DEFAULT now()
            ) ENGINE = MergeTree() PARTITION BY toYYYYMMDD(timestamp)
            ORDER BY (agent_id, timestamp) TTL timestamp + INTERVAL 3 DAY DELETE""",

            """CREATE TABLE IF NOT EXISTS audit_logs (
                id UInt64, user_id String DEFAULT 'system', username String DEFAULT 'system',
                action String, resource String DEFAULT '', details String DEFAULT '{}',
                ip String DEFAULT '', timestamp DateTime DEFAULT now()
            ) ENGINE = MergeTree() PARTITION BY toYYYYMMDD(timestamp)
            ORDER BY (user_id, timestamp) TTL timestamp + INTERVAL 90 DAY DELETE""",

            """CREATE TABLE IF NOT EXISTS reports (
                id String, report_type String, content String DEFAULT '{}',
                generated_at DateTime DEFAULT now(), sent_to String DEFAULT '[]'
            ) ENGINE = MergeTree() PARTITION BY toYYYYMMDD(generated_at)
            ORDER BY (report_type, generated_at)""",
        ]

        for sql in _config_tables + _ts_tables:
            client.command(sql)

        # ── Materialized View: latest metrics per (agent_id, metric_name) ──
        # Eliminates the expensive self-join in get_latest_metrics_per_agent()
        _mv_sql = [
            """CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_latest_mv
               ENGINE = AggregatingMergeTree()
               ORDER BY (agent_id, metric_name)
               AS SELECT
                   agent_id,
                   metric_name,
                   argMaxState(metric_value, timestamp) AS latest_value,
                   argMaxState(labels, timestamp) AS latest_labels,
                   maxState(timestamp) AS latest_ts
               FROM metrics
               GROUP BY agent_id, metric_name""",
        ]
        for sql in _mv_sql:
            try:
                client.command(sql)
            except Exception as e:
                print(f"[DB] MV creation (may already exist): {e}")

        # ── Data-skipping indexes for high-volume tables ──
        _index_sql = [
            "ALTER TABLE metrics ADD INDEX IF NOT EXISTS idx_agent_id agent_id TYPE set(100) GRANULARITY 4",
            "ALTER TABLE logs ADD INDEX IF NOT EXISTS idx_agent_id agent_id TYPE set(100) GRANULARITY 4",
            "ALTER TABLE logs ADD INDEX IF NOT EXISTS idx_log_level log_level TYPE set(10) GRANULARITY 2",
            "ALTER TABLE traces ADD INDEX IF NOT EXISTS idx_service service_name TYPE set(100) GRANULARITY 4",
            "ALTER TABLE events ADD INDEX IF NOT EXISTS idx_level level TYPE set(10) GRANULARITY 2",
        ]
        for sql in _index_sql:
            try:
                client.command(sql)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"[DB] Index creation note: {e}")

        # Insert default cluster if not exists
        existing = client.query("SELECT id FROM clusters FINAL WHERE id = 'default' AND _deleted = 0")
        if not existing.result_rows:
            _insert('clusters', ['id', 'name', 'description', 'status', '_version', '_deleted', 'created_at'],
                    [['default', 'Default Cluster', 'Default monitoring cluster', 'active', 1, 0, _now()]])

        tables = client.command("SHOW TABLES FROM insight")
        print(f"[DB] ClickHouse connected: {tables}")
        print("[DB] ClickHouse initialized successfully")
    except Exception as e:
        print(f"[DB] ClickHouse connection error: {e}")
        raise


def _parse_json_field(value, default="{}"):
    """Parse JSON field that might be string or already parsed."""
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or default)
    except (json.JSONDecodeError, TypeError):
        return json.loads(default)


# ═══════════════════════════════════════════════════════════
# User CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def create_user(username: str, password_hash: str, role: str = "admin") -> dict:
    user_id = str(uuid.uuid4())
    _insert('users', ['id', 'username', 'password_hash', 'role', '_version', '_deleted', 'created_at'],
            [[user_id, username, password_hash, role, _version(), 0, _now()]])
    return {"id": user_id, "username": username, "role": role}


def get_user_by_username(username: str) -> dict | None:
    rows = _run("SELECT * FROM users FINAL WHERE _deleted = 0 AND username = {u:String}",
                params={"u": username}, fetch=True) or []
    return rows[0] if rows else None


def get_user_by_id(user_id: str) -> dict | None:
    rows = _run("SELECT * FROM users FINAL WHERE _deleted = 0 AND id = {uid:String}",
                params={"uid": user_id}, fetch=True) or []
    return rows[0] if rows else None


def list_users() -> list[dict]:
    return _run("SELECT id, username, role, created_at FROM users FINAL WHERE _deleted = 0 ORDER BY created_at DESC",
                fetch=True) or []


def update_user_password(user_id: str, new_password_hash: str):
    user = get_user_by_id(user_id)
    if user:
        _insert('users', ['id', 'username', 'password_hash', 'role', '_version', '_deleted', 'created_at'],
                [[user_id, user['username'], new_password_hash, user.get('role', 'admin'), _version(), 0, user.get('created_at', _now())]])


def delete_user(user_id: str):
    user = get_user_by_id(user_id)
    if user:
        _insert('users', ['id', 'username', 'password_hash', 'role', '_version', '_deleted', 'created_at'],
                [[user_id, user['username'], user['password_hash'], user.get('role', 'admin'), _version(), 1, user.get('created_at', _now())]])


# ═══════════════════════════════════════════════════════════
# Cluster CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def create_cluster(name: str, description: str = "") -> dict:
    cluster_id = str(uuid.uuid4())
    _insert('clusters', ['id', 'name', 'description', 'status', '_version', '_deleted', 'created_at'],
            [[cluster_id, name, description, 'active', _version(), 0, _now()]])
    return {"id": cluster_id, "name": name, "description": description, "status": "active"}


def list_clusters() -> list[dict]:
    return _run("SELECT * FROM clusters FINAL WHERE _deleted = 0 ORDER BY created_at DESC", fetch=True) or []


def get_cluster(cluster_id: str) -> dict | None:
    rows = _run("SELECT * FROM clusters FINAL WHERE _deleted = 0 AND id = {cid:String}",
                params={"cid": cluster_id}, fetch=True) or []
    return rows[0] if rows else None


# ═══════════════════════════════════════════════════════════
# Agent CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def _resolve_category(agent_type: str, agent_category: str = None) -> str:
    if agent_category:
        return agent_category
    return "application" if agent_type in {"opentelemetry"} else "system"


def register_agent(name: str, agent_type: str, hostname: str = "", labels: dict = None,
                    cluster_id: str = "default", agent_category: str = None) -> dict:
    agent_id = str(uuid.uuid4())
    now = _now()
    category = _resolve_category(agent_type, agent_category)
    _insert('agents',
            ['id', 'name', 'agent_type', 'agent_category', 'hostname', 'cluster_id', 'status',
             'labels', 'token_id', 'agent_version', 'os_info', 'ip_address', 'last_heartbeat',
             '_version', '_deleted', 'created_at'],
            [[agent_id, name, agent_type, category, hostname, cluster_id, 'active',
              json.dumps(labels or {}), '', '', '', '', now, _version(), 0, now]])
    return {"id": agent_id, "name": name, "agent_type": agent_type, "agent_category": category, "status": "active"}


def get_agent(agent_id: str) -> dict | None:
    rows = _run("SELECT * FROM agents FINAL WHERE _deleted = 0 AND id = {aid:String}",
                params={"aid": agent_id}, fetch=True) or []
    if rows:
        rows[0]["labels"] = _parse_json_field(rows[0].get("labels"))
    return rows[0] if rows else None


def get_or_create_agent(agent_id: str, name: str, agent_type: str, hostname: str = "",
                         cluster_id: str = "default", agent_category: str = None) -> dict:
    agent = get_agent(agent_id)
    if agent:
        if agent_category and agent.get("agent_category") != agent_category:
            _upsert_agent(agent_id, agent, updates={"agent_category": agent_category})
        update_agent_heartbeat(agent_id)
        return agent
    return register_agent_with_id(agent_id, name, agent_type, hostname, cluster_id=cluster_id, agent_category=agent_category)


def register_agent_with_id(agent_id: str, name: str, agent_type: str, hostname: str = "",
                            labels: dict = None, cluster_id: str = "default", agent_category: str = None) -> dict:
    now = _now()
    category = _resolve_category(agent_type, agent_category)
    _insert('agents',
            ['id', 'name', 'agent_type', 'agent_category', 'hostname', 'cluster_id', 'status',
             'labels', 'token_id', 'agent_version', 'os_info', 'ip_address', 'last_heartbeat',
             '_version', '_deleted', 'created_at'],
            [[agent_id, name, agent_type, category, hostname, cluster_id, 'active',
              json.dumps(labels or {}), '', '', '', '', now, _version(), 0, now]])
    return {"id": agent_id, "name": name, "agent_type": agent_type, "agent_category": category, "status": "active"}


def _upsert_agent(agent_id: str, existing: dict, updates: dict = None):
    """Re-insert agent row with updated fields for ReplacingMergeTree."""
    row = {**existing, **(updates or {})}
    _insert('agents',
            ['id', 'name', 'agent_type', 'agent_category', 'hostname', 'cluster_id', 'status',
             'labels', 'token_id', 'agent_version', 'os_info', 'ip_address', 'last_heartbeat',
             '_version', '_deleted', 'created_at'],
            [[agent_id, row.get('name', ''), row.get('agent_type', 'system'), row.get('agent_category', 'system'),
              row.get('hostname', ''), row.get('cluster_id', 'default'), row.get('status', 'active'),
              json.dumps(row.get('labels', {})) if isinstance(row.get('labels'), dict) else row.get('labels', '{}'),
              row.get('token_id', ''), row.get('agent_version', ''), row.get('os_info', ''),
              row.get('ip_address', ''), row.get('last_heartbeat', _now()),
              _version(), 0, row.get('created_at', _now())]])


def list_agents(cluster_id: str = None, from_time: str = None, to_time: str = None) -> list[dict]:
    query = "SELECT * FROM agents FINAL WHERE _deleted = 0"
    params = {}
    if cluster_id and cluster_id != 'all':
        query += " AND cluster_id = {cid:String}"
        params["cid"] = cluster_id
    if from_time:
        query += " AND last_heartbeat >= {ft:String}"
        params["ft"] = from_time
    if to_time:
        query += " AND last_heartbeat <= {tt:String}"
        params["tt"] = to_time
    query += " ORDER BY created_at DESC"
    rows = _run(query, params=params, fetch=True) or []

    # Filter out agents with revoked tokens (in Python, avoids expensive subquery)
    if rows:
        token_ids = list({r.get('token_id', '') for r in rows if r.get('token_id', '')})
        revoked = set()
        if token_ids:
            for i, tid in enumerate(token_ids):
                params[f"t{i}"] = tid
            placeholders = ", ".join(f"{{t{i}:String}}" for i in range(len(token_ids)))
            inactive = _run(f"SELECT id FROM agent_tokens FINAL WHERE id IN ({placeholders}) AND (is_active = 0 OR _deleted = 1)",
                           params=params, fetch=True) or []
            revoked = {r['id'] for r in inactive}
        if revoked:
            rows = [r for r in rows if r.get('token_id', '') not in revoked]

    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
    return rows


def update_agent_heartbeat(agent_id: str):
    agent = get_agent(agent_id)
    if agent:
        _upsert_agent(agent_id, agent, updates={"last_heartbeat": _now(), "status": "active"})


def delete_agent(agent_id: str):
    """Soft-delete an agent via ReplacingMergeTree pattern."""
    agent = get_agent(agent_id)
    if agent:
        _upsert_agent(agent_id, agent, updates={"status": "deleted"})
        # Mark as deleted
        _insert('agents',
                ['id', 'name', 'agent_type', 'agent_category', 'hostname', 'cluster_id', 'status',
                 'labels', 'token_id', 'agent_version', 'os_info', 'ip_address', 'last_heartbeat',
                 '_version', '_deleted', 'created_at'],
                [[agent_id, agent.get('name', ''), agent.get('agent_type', ''), agent.get('agent_category', ''),
                  agent.get('hostname', ''), agent.get('cluster_id', ''), 'deleted',
                  json.dumps(agent.get('labels', {})) if isinstance(agent.get('labels'), dict) else agent.get('labels', '{}'),
                  agent.get('token_id', ''), agent.get('agent_version', ''), agent.get('os_info', ''),
                  agent.get('ip_address', ''), agent.get('last_heartbeat', _now()), _version(), 1, agent.get('created_at', _now())]])


def update_agent_status(agent_id: str, status: str):
    agent = get_agent(agent_id)
    if agent:
        _upsert_agent(agent_id, agent, updates={"status": status})


# ═══════════════════════════════════════════════════════════
# Agent Tokens CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def create_agent_token(name: str, agent_type: str = "any", cluster_id: str = "default", created_by: str = "") -> dict:
    import secrets as _sec
    token_id = str(uuid.uuid4())
    token_value = f"ist_{_sec.token_urlsafe(32)}"
    now = _now()
    _insert('agent_tokens',
            ['id', 'name', 'token', 'agent_type', 'cluster_id', 'created_by', 'last_used',
             'agent_count', 'is_active', '_version', '_deleted', 'created_at'],
            [[token_id, name, token_value, agent_type, cluster_id, created_by, now, 0, 1, _version(), 0, now]])
    return {"id": token_id, "name": name, "token": token_value, "agent_type": agent_type,
            "cluster_id": cluster_id, "created_by": created_by, "is_active": 1, "agent_count": 0, "created_at": now}


def list_agent_tokens() -> list[dict]:
    rows = _run("SELECT * FROM agent_tokens FINAL WHERE _deleted = 0 ORDER BY created_at DESC", fetch=True) or []
    if rows:
        # Batch count agents per token (single query instead of N+1)
        counts = _run("SELECT token_id, count() as cnt FROM agents FINAL WHERE _deleted = 0 AND token_id != '' GROUP BY token_id",
                      fetch=True) or []
        count_map = {r["token_id"]: r["cnt"] for r in counts}
        for r in rows:
            r["agent_count"] = count_map.get(r["id"], 0)
    return rows


def verify_agent_token(token: str) -> dict | None:
    rows = _run("SELECT * FROM agent_tokens FINAL WHERE _deleted = 0 AND token = {t:String} AND is_active = 1",
                params={"t": token}, fetch=True) or []
    if not rows:
        return None
    # Update last_used
    rec = rows[0]
    _insert('agent_tokens',
            ['id', 'name', 'token', 'agent_type', 'cluster_id', 'created_by', 'last_used',
             'agent_count', 'is_active', '_version', '_deleted', 'created_at'],
            [[rec['id'], rec['name'], rec['token'], rec.get('agent_type', 'any'),
              rec.get('cluster_id', 'default'), rec.get('created_by', ''), _now(),
              rec.get('agent_count', 0), 1, _version(), 0, rec.get('created_at', _now())]])
    return rec


def revoke_agent_token(token_id: str) -> bool:
    rec = _run("SELECT * FROM agent_tokens FINAL WHERE _deleted = 0 AND id = {tid:String}",
               params={"tid": token_id}, fetch=True)
    if rec:
        rec = rec[0]
        # Mark token inactive
        _insert('agent_tokens',
                ['id', 'name', 'token', 'agent_type', 'cluster_id', 'created_by', 'last_used',
                 'agent_count', 'is_active', '_version', '_deleted', 'created_at'],
                [[rec['id'], rec['name'], rec['token'], rec.get('agent_type', 'any'),
                  rec.get('cluster_id', 'default'), rec.get('created_by', ''), rec.get('last_used', _now()),
                  rec.get('agent_count', 0), 0, _version(), 0, rec.get('created_at', _now())]])
    # Mark linked agents as deleted
    agents = _run("SELECT * FROM agents FINAL WHERE _deleted = 0 AND token_id = {tid:String}",
                  params={"tid": token_id}, fetch=True) or []
    for a in agents:
        _upsert_agent(a['id'], a, updates={"_deleted_flag": True})
        _insert('agents',
                ['id', 'name', 'agent_type', 'agent_category', 'hostname', 'cluster_id', 'status',
                 'labels', 'token_id', 'agent_version', 'os_info', 'ip_address', 'last_heartbeat',
                 '_version', '_deleted', 'created_at'],
                [[a['id'], a.get('name', ''), a.get('agent_type', ''), a.get('agent_category', ''),
                  a.get('hostname', ''), a.get('cluster_id', ''), 'inactive',
                  json.dumps(a.get('labels', {})) if isinstance(a.get('labels'), dict) else a.get('labels', '{}'),
                  a.get('token_id', ''), a.get('agent_version', ''), a.get('os_info', ''),
                  a.get('ip_address', ''), a.get('last_heartbeat', _now()), _version(), 1, a.get('created_at', _now())]])
    return True


def get_agents_by_token(token_id: str) -> list[dict]:
    rows = _run("SELECT * FROM agents FINAL WHERE _deleted = 0 AND token_id = {tid:String} ORDER BY created_at DESC",
                params={"tid": token_id}, fetch=True) or []
    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
    return rows


def connect_agent(token_record: dict, agent_data: dict) -> dict:
    now = _now()
    agent_id = agent_data.get("agent_id") or str(uuid.uuid4())
    name = agent_data.get("name", agent_data.get("hostname", "unnamed"))
    agent_type = agent_data.get("agent_type", token_record.get("agent_type", "system"))
    if agent_type == "any":
        agent_type = agent_data.get("agent_type", "system")
    category = _resolve_category(agent_type, agent_data.get("agent_category"))
    hostname = agent_data.get("hostname", "")
    cluster_id = agent_data.get("cluster_id", token_record.get("cluster_id", "default"))
    labels_val = json.dumps(agent_data.get("labels", {}))
    version = agent_data.get("version", "")
    os_info = agent_data.get("os_info", "")
    ip_address = agent_data.get("ip_address", "")
    token_id = token_record["id"]

    _insert('agents',
            ['id', 'name', 'agent_type', 'agent_category', 'hostname', 'cluster_id', 'status',
             'labels', 'token_id', 'agent_version', 'os_info', 'ip_address', 'last_heartbeat',
             '_version', '_deleted', 'created_at'],
            [[agent_id, name, agent_type, category, hostname, cluster_id, 'active',
              labels_val, token_id, version, os_info, ip_address, now, _version(), 0, now]])
    return {"id": agent_id, "name": name, "agent_type": agent_type, "agent_category": category,
            "status": "active", "token_id": token_id, "agent_version": version}


def migrate_agent_tokens_table():
    """No-op — tables are created by init-schema.sql on ClickHouse."""
    pass


# ═══════════════════════════════════════════════════════════
# Metrics CRUD (MergeTree — time-series)
# ═══════════════════════════════════════════════════════════

def insert_metrics(agent_id: str, metrics: list[dict]):
    rows = []
    for m in metrics:
        ts = m.get("timestamp", _now())
        rows.append([0, agent_id, m.get("metric_name", ""), m.get("metric_value", 0),
                     json.dumps(m.get("labels", {})), ts])
    _insert('metrics', ['id', 'agent_id', 'metric_name', 'metric_value', 'labels', 'timestamp'], rows)


def get_metrics(agent_id: str = None, metric_name: str = None, last_hours: int = 24,
                limit: int = 1000, from_time: str = None, to_time: str = None) -> list[dict]:
    cutoff = from_time or (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    query = "SELECT * FROM metrics WHERE timestamp >= {cutoff:String}"
    params = {"cutoff": cutoff}
    if to_time:
        query += " AND timestamp <= {to_time:String}"; params["to_time"] = to_time
    if agent_id:
        query += " AND agent_id = {agent_id:String}"; params["agent_id"] = agent_id
    if metric_name:
        query += " AND metric_name = {metric_name:String}"; params["metric_name"] = metric_name
    query += " ORDER BY timestamp DESC LIMIT {lim:UInt32}"
    params["lim"] = limit
    rows = _run(query, params=params, fetch=True) or []
    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
    return rows


def get_latest_metrics_per_agent() -> dict[str, list[dict]]:
    # Use Materialized View for O(1) lookup instead of self-join
    # Falls back to direct query if MV doesn't exist yet
    try:
        query = """SELECT agent_id, metric_name,
                          argMaxMerge(latest_value) AS metric_value,
                          argMaxMerge(latest_labels) AS labels,
                          maxMerge(latest_ts) AS timestamp
                   FROM metrics_latest_mv
                   GROUP BY agent_id, metric_name
                   ORDER BY agent_id, metric_name"""
        rows = _run(query, fetch=True) or []
    except Exception:
        # Fallback: direct query with LIMIT for safety
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S')
        query = """SELECT agent_id, metric_name, metric_value, labels, timestamp
                   FROM metrics WHERE timestamp >= {cutoff:String}
                   ORDER BY timestamp DESC
                   LIMIT 10000"""
        rows = _run(query, params={"cutoff": cutoff}, fetch=True) or []
        # Deduplicate: keep only latest per (agent_id, metric_name)
        seen = set()
        deduped = []
        for r in rows:
            key = (r["agent_id"], r["metric_name"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        rows = deduped

    result: dict[str, list[dict]] = {}
    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
        aid = r["agent_id"]
        if aid not in result:
            result[aid] = []
        result[aid].append(r)
    return result


def get_metrics_timeseries(agent_id: str = None, last_hours: int = 6, metric_names: list[str] = None) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    # Aggregate in ClickHouse instead of fetching all raw rows
    query = """SELECT
                  formatDateTime(timestamp, '%Y-%m-%d %H:%i') AS time,
                  metric_name,
                  round(avg(metric_value), 2) AS metric_value
               FROM metrics WHERE timestamp >= {cutoff:String}"""
    params = {"cutoff": cutoff}
    if agent_id:
        query += " AND agent_id = {agent_id:String}"; params["agent_id"] = agent_id
    if metric_names:
        for i, n in enumerate(metric_names):
            params[f"mn_{i}"] = n
        placeholders = ", ".join(f"{{mn_{i}:String}}" for i in range(len(metric_names)))
        query += f" AND metric_name IN ({placeholders})"
    query += " GROUP BY time, metric_name ORDER BY time ASC"
    rows = _run(query, params=params, fetch=True) or []
    # Pivot: group by time, metric_name as columns
    time_map: dict[str, dict] = {}
    for r in rows:
        ts = r["time"]
        if ts not in time_map:
            time_map[ts] = {"time": ts}
        time_map[ts][r["metric_name"]] = r["metric_value"]
    return list(time_map.values())


# ═══════════════════════════════════════════════════════════
# Events CRUD (MergeTree — time-series)
# ═══════════════════════════════════════════════════════════

def get_event_counts_by_hour(last_hours: int = 24) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    query = """SELECT formatDateTime(created_at, '%Y-%m-%d %H:00') as hour,
                      level, count() as count
               FROM events WHERE created_at >= {cutoff:String}
               GROUP BY hour, level ORDER BY hour ASC"""
    rows = _run(query, params={"cutoff": cutoff}, fetch=True) or []
    hour_map: dict[str, dict] = {}
    for r in rows:
        h = r["hour"]
        if h not in hour_map:
            hour_map[h] = {"hour": h, "critical": 0, "error": 0, "warning": 0, "info": 0}
        hour_map[h][r["level"]] = r["count"]
    return list(hour_map.values())


def insert_events(agent_id: str, events: list[dict]):
    rows = []
    for e in events:
        event_id = str(uuid.uuid4())
        ts = e.get("timestamp", _now())
        rows.append([event_id, agent_id, e.get("level", "info"), e.get("title", ""), e.get("message", ""),
                     e.get("source", ""), e.get("namespace", ""), e.get("resource", ""),
                     json.dumps(e.get("details", {})), 0, ts])
    _insert('events', ['id', 'agent_id', 'level', 'title', 'message', 'source', 'namespace',
                        'resource', 'details', 'acknowledged', 'created_at'], rows)


def get_events(agent_id: str = None, level: str = None, last_hours: int = 24,
               limit: int = 200, from_time: str = None, to_time: str = None) -> list[dict]:
    cutoff = from_time or (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    query = "SELECT * FROM events WHERE created_at >= {cutoff:String}"
    params = {"cutoff": cutoff}
    if to_time:
        query += " AND created_at <= {to_time:String}"; params["to_time"] = to_time
    if agent_id:
        query += " AND agent_id = {agent_id:String}"; params["agent_id"] = agent_id
    if level:
        query += " AND level = {level:String}"; params["level"] = level
    query += " ORDER BY created_at DESC LIMIT {lim:UInt32}"
    params["lim"] = limit
    rows = _run(query, params=params, fetch=True) or []
    for r in rows:
        r["details"] = _parse_json_field(r.get("details"))
    return rows


def get_event_counts(last_hours: int = 24) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    rows = _run("SELECT level, count() as cnt FROM events WHERE created_at >= {cutoff:String} GROUP BY level",
                params={"cutoff": cutoff}, fetch=True) or []
    return {r["level"]: r["cnt"] for r in rows}


def acknowledge_event(event_id: str):
    # ClickHouse doesn't support UPDATE — use ALTER TABLE UPDATE for MergeTree
    _run("ALTER TABLE events UPDATE acknowledged = 1 WHERE id = {eid:String}",
         params={"eid": event_id})


# ═══════════════════════════════════════════════════════════
# Logs CRUD (MergeTree — time-series)
# ═══════════════════════════════════════════════════════════

def insert_logs(agent_id: str, logs: list[dict]):
    rows = []
    for log in logs:
        ts = log.get("timestamp", _now())
        rows.append([0, agent_id, log.get("namespace", ""), log.get("pod_name", ""),
                     log.get("container", ""), log.get("log_level", "error"), log.get("message", ""), ts])
    _insert('logs', ['id', 'agent_id', 'namespace', 'pod_name', 'container', 'log_level', 'message', 'timestamp'], rows)


def get_logs(agent_id: str = None, last_hours: int = 24, limit: int = 500,
             from_time: str = None, to_time: str = None) -> list[dict]:
    cutoff = from_time or (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    query = "SELECT * FROM logs WHERE timestamp >= {cutoff:String}"
    params = {"cutoff": cutoff}
    if to_time:
        query += " AND timestamp <= {to_time:String}"; params["to_time"] = to_time
    if agent_id:
        query += " AND agent_id = {agent_id:String}"; params["agent_id"] = agent_id
    query += " ORDER BY timestamp DESC LIMIT {lim:UInt32}"
    params["lim"] = limit
    return _run(query, params=params, fetch=True) or []


# ═══════════════════════════════════════════════════════════
# Alert Config CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def save_alert_config(channel: str, config: dict, enabled: bool = True, alert_levels: list[str] = None) -> dict:
    config_id = str(uuid.uuid4())
    _insert('alert_configs',
            ['id', 'channel', 'config', 'enabled', 'alert_levels', '_version', '_deleted', 'created_at'],
            [[config_id, channel, json.dumps(config), 1 if enabled else 0,
              json.dumps(alert_levels or ["critical", "error"]), _version(), 0, _now()]])
    return {"id": config_id, "channel": channel, "enabled": enabled}


def get_alert_configs(channel: str = None) -> list[dict]:
    query = "SELECT * FROM alert_configs FINAL WHERE _deleted = 0"
    params = {}
    if channel:
        query += " AND channel = {ch:String}"; params["ch"] = channel
    rows = _run(query, params=params, fetch=True) or []
    for r in rows:
        r["config"] = _parse_json_field(r.get("config"))
        r["alert_levels"] = _parse_json_field(r.get("alert_levels"), "[]")
        r["enabled"] = bool(r.get("enabled", 0))
    return rows


def delete_alert_config(config_id: str):
    rec = _run("SELECT * FROM alert_configs FINAL WHERE _deleted = 0 AND id = {cid:String}",
               params={"cid": config_id}, fetch=True)
    if rec:
        r = rec[0]
        _insert('alert_configs',
                ['id', 'channel', 'config', 'enabled', 'alert_levels', '_version', '_deleted', 'created_at'],
                [[r['id'], r['channel'], r.get('config', '{}'), r.get('enabled', 0),
                  r.get('alert_levels', '[]'), _version(), 1, r.get('created_at', _now())]])


# ═══════════════════════════════════════════════════════════
# Notification Rules CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def save_rule(name: str, metric_name: str, operator: str, threshold: float,
              duration_minutes: int = 5, channels: list[str] = None) -> dict:
    rule_id = str(uuid.uuid4())
    _insert('notification_rules',
            ['id', 'name', 'metric_name', 'operator', 'threshold', 'duration_minutes',
             'channels', 'enabled', '_version', '_deleted', 'created_at'],
            [[rule_id, name, metric_name, operator, threshold, duration_minutes,
              json.dumps(channels or ["telegram"]), 1, _version(), 0, _now()]])
    return {"id": rule_id, "name": name, "metric_name": metric_name, "operator": operator, "threshold": threshold}


def get_rules(enabled_only: bool = False) -> list[dict]:
    query = "SELECT * FROM notification_rules FINAL WHERE _deleted = 0"
    if enabled_only:
        query += " AND enabled = 1"
    query += " ORDER BY created_at DESC"
    rows = _run(query, fetch=True) or []
    for r in rows:
        r["channels"] = _parse_json_field(r.get("channels"), "[]")
        r["enabled"] = bool(r.get("enabled", 0))
    return rows


def delete_rule(rule_id: str):
    rec = _run("SELECT * FROM notification_rules FINAL WHERE _deleted = 0 AND id = {rid:String}",
               params={"rid": rule_id}, fetch=True)
    if rec:
        r = rec[0]
        _insert('notification_rules',
                ['id', 'name', 'metric_name', 'operator', 'threshold', 'duration_minutes',
                 'channels', 'enabled', '_version', '_deleted', 'created_at'],
                [[r['id'], r['name'], r['metric_name'], r['operator'], r['threshold'],
                  r.get('duration_minutes', 5), r.get('channels', '[]'), r.get('enabled', 0),
                  _version(), 1, r.get('created_at', _now())]])


def toggle_rule(rule_id: str, enabled: bool):
    rec = _run("SELECT * FROM notification_rules FINAL WHERE _deleted = 0 AND id = {rid:String}",
               params={"rid": rule_id}, fetch=True)
    if rec:
        r = rec[0]
        _insert('notification_rules',
                ['id', 'name', 'metric_name', 'operator', 'threshold', 'duration_minutes',
                 'channels', 'enabled', '_version', '_deleted', 'created_at'],
                [[r['id'], r['name'], r['metric_name'], r['operator'], r['threshold'],
                  r.get('duration_minutes', 5), r.get('channels', '[]'), 1 if enabled else 0,
                  _version(), 0, r.get('created_at', _now())]])


# ═══════════════════════════════════════════════════════════
# Reports CRUD (MergeTree — append-only)
# ═══════════════════════════════════════════════════════════

def save_report(report_type: str, content: dict, sent_to: list[str] = None) -> dict:
    report_id = str(uuid.uuid4())
    now = _now()
    def _json_default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        raise TypeError(f'Object of type {o.__class__.__name__} is not JSON serializable')
    _insert('reports', ['id', 'report_type', 'content', 'generated_at', 'sent_to'],
            [[report_id, report_type, json.dumps(content, default=_json_default), now, json.dumps(sent_to or [])]])
    return {"id": report_id, "report_type": report_type, "generated_at": now}


def get_reports(limit: int = 20) -> list[dict]:
    rows = _run("SELECT * FROM reports ORDER BY generated_at DESC LIMIT {lim:UInt32}",
                params={"lim": limit}, fetch=True) or []
    for r in rows:
        r["content"] = _parse_json_field(r.get("content"))
        r["sent_to"] = _parse_json_field(r.get("sent_to"), "[]")
    return rows


# ═══════════════════════════════════════════════════════════
# Settings CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def get_setting(key: str, default: Any = None) -> Any:
    rows = _run("SELECT value FROM settings FINAL WHERE _deleted = 0 AND key = {k:String}",
                params={"k": key}, fetch=True) or []
    if rows:
        return _parse_json_field(rows[0]["value"])
    return default


def set_setting(key: str, value: Any):
    serialized = json.dumps(value)
    _insert('settings', ['key', 'value', '_version', '_deleted', 'updated_at'],
            [[key, serialized, _version(), 0, _now()]])


# ═══════════════════════════════════════════════════════════
# Audit Log CRUD (MergeTree — time-series)
# ═══════════════════════════════════════════════════════════

def insert_audit_log(user_id: str = "system", username: str = "system", action: str = "",
                     resource: str = "", details: dict = None, ip: str = ""):
    _insert('audit_logs', ['id', 'user_id', 'username', 'action', 'resource', 'details', 'ip', 'timestamp'],
            [[0, user_id, username, action, resource, json.dumps(details or {}), ip, _now()]])


def get_audit_logs(last_hours: int = 168, limit: int = 100) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    rows = _run("SELECT * FROM audit_logs WHERE timestamp >= {cutoff:String} ORDER BY timestamp DESC LIMIT {lim:UInt32}",
                params={"cutoff": cutoff, "lim": limit}, fetch=True) or []
    for r in rows:
        r["details"] = _parse_json_field(r.get("details"))
    return rows


# ═══════════════════════════════════════════════════════════
# Webhooks CRUD (ReplacingMergeTree)
# ═══════════════════════════════════════════════════════════

def save_webhook(name: str, url: str, wh_type: str = "custom", events: list[str] = None) -> dict:
    wh_id = str(uuid.uuid4())
    _insert('webhooks',
            ['id', 'name', 'url', 'type', 'events', 'enabled', '_version', '_deleted', 'created_at'],
            [[wh_id, name, url, wh_type, json.dumps(events or ["critical", "error"]), 1, _version(), 0, _now()]])
    return {"id": wh_id, "name": name, "url": url, "type": wh_type}


def get_webhooks(enabled_only: bool = False) -> list[dict]:
    query = "SELECT * FROM webhooks FINAL WHERE _deleted = 0"
    if enabled_only:
        query += " AND enabled = 1"
    rows = _run(query, fetch=True) or []
    for r in rows:
        r["events"] = _parse_json_field(r.get("events"), "[]")
        r["enabled"] = bool(r.get("enabled", 0))
    return rows


def delete_webhook(wh_id: str):
    rec = _run("SELECT * FROM webhooks FINAL WHERE _deleted = 0 AND id = {wid:String}",
               params={"wid": wh_id}, fetch=True)
    if rec:
        r = rec[0]
        _insert('webhooks',
                ['id', 'name', 'url', 'type', 'events', 'enabled', '_version', '_deleted', 'created_at'],
                [[r['id'], r['name'], r['url'], r.get('type', 'custom'), r.get('events', '[]'),
                  r.get('enabled', 0), _version(), 1, r.get('created_at', _now())]])


def toggle_webhook(wh_id: str, enabled: bool):
    rec = _run("SELECT * FROM webhooks FINAL WHERE _deleted = 0 AND id = {wid:String}",
               params={"wid": wh_id}, fetch=True)
    if rec:
        r = rec[0]
        _insert('webhooks',
                ['id', 'name', 'url', 'type', 'events', 'enabled', '_version', '_deleted', 'created_at'],
                [[r['id'], r['name'], r['url'], r.get('type', 'custom'), r.get('events', '[]'),
                  1 if enabled else 0, _version(), 0, r.get('created_at', _now())]])


# ═══════════════════════════════════════════════════════════
# Process Snapshots (MergeTree)
# ═══════════════════════════════════════════════════════════

def save_process_snapshot(agent_id: str, processes: list[dict]):
    snapshot_val = json.dumps(processes)
    _run("ALTER TABLE processes DELETE WHERE agent_id = {agent_id:String}", params={"agent_id": agent_id})
    _insert('processes', ['id', 'agent_id', 'snapshot', 'timestamp'],
            [[0, agent_id, snapshot_val, _now()]])


def get_process_snapshot(agent_id: str) -> list[dict]:
    rows = _run("SELECT snapshot, timestamp FROM processes WHERE agent_id = {agent_id:String} ORDER BY timestamp DESC LIMIT 1",
                params={"agent_id": agent_id}, fetch=True) or []
    if rows:
        return {"processes": _parse_json_field(rows[0].get("snapshot"), "[]"), "timestamp": rows[0].get("timestamp")}
    return {"processes": [], "timestamp": None}


# ═══════════════════════════════════════════════════════════
# Traces (MergeTree — time-series)
# ═══════════════════════════════════════════════════════════

def insert_traces(agent_id: str, traces: list[dict]):
    rows = []
    for t in traces:
        trace_id = t.get("trace_id", str(uuid.uuid4()))
        span_id = t.get("span_id", str(uuid.uuid4()))
        rows.append([span_id, agent_id, trace_id, t.get("span_name", ""), t.get("service_name", ""),
                     t.get("duration_ms", 0), t.get("status", "ok"), json.dumps(t.get("attributes", {})), _now()])
    _insert('traces', ['id', 'agent_id', 'trace_id', 'span_name', 'service_name',
                        'duration_ms', 'status', 'attributes', 'timestamp'], rows)


def get_traces(agent_id: str = None, last_hours: int = 24, limit: int = 100,
               from_time: str = None, to_time: str = None) -> list[dict]:
    cutoff = from_time or (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    query = "SELECT * FROM traces WHERE timestamp >= {cutoff:String}"
    params = {"cutoff": cutoff}
    if to_time:
        query += " AND timestamp <= {to_time:String}"; params["to_time"] = to_time
    if agent_id:
        query += " AND agent_id = {agent_id:String}"; params["agent_id"] = agent_id
    query += " ORDER BY timestamp DESC LIMIT {lim:UInt32}"
    params["lim"] = limit
    rows = _run(query, params=params, fetch=True) or []
    for r in rows:
        r["attributes"] = _parse_json_field(r.get("attributes"))
    return rows


def get_trace_summary(last_hours: int = 1) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    rows = _run("""
        SELECT service_name,
               count() as req_count,
               avg(duration_ms) as avg_latency,
               max(duration_ms) as max_latency,
               quantile(0.95)(duration_ms) as p95_latency,
               countIf(status = 'error') as error_count
        FROM traces WHERE timestamp >= {cutoff:String}
        GROUP BY service_name ORDER BY req_count DESC
    """, params={"cutoff": cutoff}, fetch=True) or []

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


# ═══════════════════════════════════════════════════════════
# Storage Stats & Retention
# ═══════════════════════════════════════════════════════════

def get_storage_stats() -> dict:
    try:
        rows = _run("""
            SELECT table, formatReadableSize(sum(bytes_on_disk)) as size,
                   sum(rows) as row_count,
                   min(min_date) as oldest_data, max(max_date) as newest_data
            FROM system.parts
            WHERE database = 'insight' AND active = 1
            GROUP BY table ORDER BY sum(bytes_on_disk) DESC
        """, fetch=True) or []
        ttl_rows = _run("""
            SELECT name as table, engine, create_table_query
            FROM system.tables WHERE database = 'insight'
        """, fetch=True) or []
        ttl_map = {}
        for t in ttl_rows:
            q = str(t.get("create_table_query", ""))
            import re
            m = re.search(r'TTL\s+\w+\s*\+\s*(?:toIntervalDay\((\d+)\)|INTERVAL\s+(\d+)\s+DAY)', q, re.IGNORECASE)
            if m:
                ttl_map[t["table"]] = int(m.group(1) or m.group(2))
        tables = [{
            "name": r["table"], "size": r["size"], "rows": r["row_count"],
            "oldest": str(r.get("oldest_data", "")), "newest": str(r.get("newest_data", "")),
            "retention_days": ttl_map.get(r["table"], None),
        } for r in rows]
        return {"engine": "clickhouse", "tables": tables}
    except Exception as e:
        return {"engine": "clickhouse", "tables": [], "error": str(e)}


def apply_retention_policies() -> dict:
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
            _run(f"ALTER TABLE {table} MODIFY TTL {col} + INTERVAL {days} DAY DELETE")
            results[table] = {"days": days, "status": "applied"}
        except Exception as e:
            results[table] = {"days": days, "status": "error", "error": str(e)}
    return {"status": "ok", "retention": results}


def purge_all_data() -> dict:
    tables = ["metrics", "logs", "traces", "events"]
    results = {}
    for table in tables:
        try:
            _run(f"TRUNCATE TABLE {table}")
            results[table] = "purged"
        except Exception as e:
            results[table] = f"error: {e}"
    return {"status": "ok", "tables": results}


# ═══════════════════════════════════════════════════════════
# Service-level queries
# ═══════════════════════════════════════════════════════════

def get_services(last_hours: int = 24) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    return _run(
        "SELECT service_name, count() as req_count, avg(duration_ms) as avg_latency, "
        "countIf(status = 'error') as error_count, max(timestamp) as last_seen "
        "FROM traces WHERE timestamp >= {cutoff:String} AND service_name != '' "
        "GROUP BY service_name ORDER BY req_count DESC",
        params={"cutoff": cutoff}, fetch=True
    ) or []


def get_traces_by_service(service_name: str, last_hours: int = 24, limit: int = 100) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    rows = _run(
        "SELECT * FROM traces WHERE service_name = {svc:String} AND timestamp >= {cutoff:String} "
        "ORDER BY timestamp DESC LIMIT {lim:UInt32}",
        params={"svc": service_name, "cutoff": cutoff, "lim": limit}, fetch=True
    ) or []
    for r in rows:
        r["attributes"] = _parse_json_field(r.get("attributes"))
    return rows


def get_metrics_by_service(service_name: str, last_hours: int = 24, limit: int = 500) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).strftime('%Y-%m-%d %H:%M:%S')
    # Use agent_id lookup from traces instead of LIKE scan on JSON labels
    rows = _run(
        """SELECT m.* FROM metrics m
           WHERE m.agent_id IN (
               SELECT DISTINCT agent_id FROM traces
               WHERE service_name = {svc:String} AND timestamp >= {cutoff:String}
           ) AND m.timestamp >= {cutoff:String}
           ORDER BY m.timestamp DESC LIMIT {lim:UInt32}""",
        params={"svc": service_name, "cutoff": cutoff, "lim": limit}, fetch=True
    ) or []
    for r in rows:
        r["labels"] = _parse_json_field(r.get("labels"))
    return rows
