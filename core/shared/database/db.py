"""
Insight Monitoring System - Database Connection & Operations
Uses SQLite for MVP (can swap to PostgreSQL via DATABASE_URL env var).
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

DATABASE_URL = os.getenv("DATABASE_URL", "insight.db")

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    hostname TEXT DEFAULT '',
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

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,
    content TEXT DEFAULT '{}',
    generated_at TEXT DEFAULT (datetime('now')),
    sent_to TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


def get_db_path() -> str:
    return DATABASE_URL


@contextmanager
def get_connection():
    conn = sqlite3.connect(get_db_path())
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


def init_db():
    with get_connection() as conn:
        conn.executescript(_CREATE_TABLES)
    print("[DB] Database initialized successfully")


# ─── Agent CRUD ───


def register_agent(name: str, agent_type: str, hostname: str = "", labels: dict = None) -> dict:
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, agent_type, hostname, status, labels, last_heartbeat, created_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
            (agent_id, name, agent_type, hostname, json.dumps(labels or {}), now, now),
        )
    return {"id": agent_id, "name": name, "agent_type": agent_type, "status": "active"}


def get_agent(agent_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return dict(row) if row else None


def get_or_create_agent(agent_id: str, name: str, agent_type: str, hostname: str = "") -> dict:
    agent = get_agent(agent_id)
    if agent:
        update_agent_heartbeat(agent_id)
        return agent
    return register_agent_with_id(agent_id, name, agent_type, hostname)


def register_agent_with_id(agent_id: str, name: str, agent_type: str, hostname: str = "", labels: dict = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO agents (id, name, agent_type, hostname, status, labels, last_heartbeat, created_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
            (agent_id, name, agent_type, hostname, json.dumps(labels or {}), now, now),
        )
    return {"id": agent_id, "name": name, "agent_type": agent_type, "status": "active"}


def list_agents() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM agents ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_agent_heartbeat(agent_id: str):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE agents SET last_heartbeat = ?, status = 'active' WHERE id = ?",
            (now, agent_id),
        )


def update_agent_status(agent_id: str, status: str):
    with get_connection() as conn:
        conn.execute("UPDATE agents SET status = ? WHERE id = ?", (status, agent_id))


# ─── Metrics CRUD ───


def insert_metrics(agent_id: str, metrics: list[dict]):
    with get_connection() as conn:
        for m in metrics:
            conn.execute(
                "INSERT INTO metrics (agent_id, metric_name, metric_value, labels, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    agent_id,
                    m.get("metric_name", ""),
                    m.get("metric_value", 0),
                    json.dumps(m.get("labels", {})),
                    m.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ),
            )


def get_metrics(agent_id: str = None, metric_name: str = None, last_hours: int = 24, limit: int = 1000) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).isoformat()
    query = "SELECT * FROM metrics WHERE timestamp >= ?"
    params: list[Any] = [cutoff]

    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if metric_name:
        query += " AND metric_name = ?"
        params.append(metric_name)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["labels"] = json.loads(d.get("labels", "{}"))
        results.append(d)
    return results


def get_latest_metrics_per_agent() -> dict[str, list[dict]]:
    """Get the most recent metrics grouped by agent."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT m.* FROM metrics m
               INNER JOIN (
                   SELECT agent_id, metric_name, MAX(timestamp) as max_ts
                   FROM metrics
                   GROUP BY agent_id, metric_name
               ) latest ON m.agent_id = latest.agent_id
                   AND m.metric_name = latest.metric_name
                   AND m.timestamp = latest.max_ts
               ORDER BY m.agent_id, m.metric_name"""
        ).fetchall()

    result: dict[str, list[dict]] = {}
    for r in rows:
        d = dict(r)
        d["labels"] = json.loads(d.get("labels", "{}"))
        aid = d["agent_id"]
        if aid not in result:
            result[aid] = []
        result[aid].append(d)
    return result


# ─── Events CRUD ───


def insert_events(agent_id: str, events: list[dict]):
    with get_connection() as conn:
        for e in events:
            event_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO events (id, agent_id, level, title, message, source, namespace, resource, details, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    agent_id,
                    e.get("level", "info"),
                    e.get("title", ""),
                    e.get("message", ""),
                    e.get("source", ""),
                    e.get("namespace", ""),
                    e.get("resource", ""),
                    json.dumps(e.get("details", {})),
                    e.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ),
            )


def get_events(agent_id: str = None, level: str = None, last_hours: int = 24, limit: int = 200) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).isoformat()
    query = "SELECT * FROM events WHERE created_at >= ?"
    params: list[Any] = [cutoff]

    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if level:
        query += " AND level = ?"
        params.append(level)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d.get("details", "{}"))
        results.append(d)
    return results


def get_event_counts(last_hours: int = 24) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT level, COUNT(*) as cnt FROM events WHERE created_at >= ? GROUP BY level",
            (cutoff,),
        ).fetchall()
    return {r["level"]: r["cnt"] for r in rows}


def acknowledge_event(event_id: str):
    with get_connection() as conn:
        conn.execute("UPDATE events SET acknowledged = 1 WHERE id = ?", (event_id,))


# ─── Logs CRUD ───


def insert_logs(agent_id: str, logs: list[dict]):
    with get_connection() as conn:
        for log in logs:
            conn.execute(
                "INSERT INTO logs (agent_id, namespace, pod_name, container, log_level, message, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    agent_id,
                    log.get("namespace", ""),
                    log.get("pod_name", ""),
                    log.get("container", ""),
                    log.get("log_level", "error"),
                    log.get("message", ""),
                    log.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ),
            )


def get_logs(agent_id: str = None, last_hours: int = 24, limit: int = 500) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=last_hours)).isoformat()
    query = "SELECT * FROM logs WHERE timestamp >= ?"
    params: list[Any] = [cutoff]

    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ─── Alert Config CRUD ───


def save_alert_config(channel: str, config: dict, enabled: bool = True, alert_levels: list[str] = None) -> dict:
    config_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO alert_configs (id, channel, config, enabled, alert_levels) VALUES (?, ?, ?, ?, ?)",
            (
                config_id,
                channel,
                json.dumps(config),
                1 if enabled else 0,
                json.dumps(alert_levels or ["critical", "error"]),
            ),
        )
    return {"id": config_id, "channel": channel, "enabled": enabled}


def get_alert_configs(channel: str = None) -> list[dict]:
    query = "SELECT * FROM alert_configs"
    params = []
    if channel:
        query += " WHERE channel = ?"
        params.append(channel)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["config"] = json.loads(d.get("config", "{}"))
        d["alert_levels"] = json.loads(d.get("alert_levels", "[]"))
        d["enabled"] = bool(d.get("enabled", 0))
        results.append(d)
    return results


def delete_alert_config(config_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM alert_configs WHERE id = ?", (config_id,))


# ─── Reports CRUD ───


def save_report(report_type: str, content: dict, sent_to: list[str] = None) -> dict:
    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO reports (id, report_type, content, generated_at, sent_to) VALUES (?, ?, ?, ?, ?)",
            (report_id, report_type, json.dumps(content), now, json.dumps(sent_to or [])),
        )
    return {"id": report_id, "report_type": report_type, "generated_at": now}


def get_reports(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY generated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["content"] = json.loads(d.get("content", "{}"))
        d["sent_to"] = json.loads(d.get("sent_to", "[]"))
        results.append(d)
    return results


# ─── Settings CRUD ───


def get_setting(key: str, default: Any = None) -> Any:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]
    return default


def set_setting(key: str, value: Any):
    now = datetime.now(timezone.utc).isoformat()
    serialized = json.dumps(value) if not isinstance(value, str) else value
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, serialized, now),
        )
