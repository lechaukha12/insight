"""
Insight Monitoring System - API Gateway v4.0.0
Main FastAPI application with JWT auth, clusters, rules, WebSocket, and audit logging.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.db import (
    init_db,
    register_agent, get_or_create_agent, list_agents, get_agent,
    update_agent_heartbeat,
    insert_metrics, get_metrics, get_latest_metrics_per_agent,
    get_metrics_timeseries, get_event_counts_by_hour,
    insert_events, get_events, get_event_counts, acknowledge_event,
    insert_logs, get_logs,
    save_alert_config, get_alert_configs, delete_alert_config,
    save_report, get_reports,
    get_setting, set_setting,
    create_user, get_user_by_username, get_user_by_id,
    create_cluster, list_clusters, get_cluster,
    save_rule, get_rules, delete_rule, toggle_rule,
    insert_audit_log, get_audit_logs,
)
from api_gateway.auth import (
    hash_password, verify_password, create_token, verify_token, ensure_default_admin,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("insight.gateway")

# ─── WebSocket Manager ───

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WS client connected ({len(self.active_connections)} total)")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WS client disconnected ({len(self.active_connections)} total)")

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

ws_manager = ConnectionManager()


# ─── Lifespan ───

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Insight API Gateway v4.0.0 starting...")
    init_db()
    ensure_default_admin()
    logger.info("Database and auth initialized")
    yield
    logger.info("Insight API Gateway shutting down")


# ─── App ───

app = FastAPI(
    title="Insight Monitoring System",
    description="Central monitoring platform for multi-agent infrastructure monitoring",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")


# ─── Auth Dependencies ───

def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def get_current_user(request: Request) -> dict | None:
    """Extract user from JWT token. Returns None for unauthenticated requests."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    payload = verify_token(token)
    if not payload:
        return None
    return {"id": payload["sub"], "username": payload["username"], "role": payload.get("role", "admin")}


async def require_auth(request: Request) -> dict:
    """Require valid JWT token. Raises 401 if not authenticated."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ─── Health ───

@app.get("/health")
async def health():
    return {"status": "ok", "service": "insight-api-gateway", "version": "4.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/")
async def root():
    return {
        "name": "Insight Monitoring System", "version": "4.0.0",
        "endpoints": {
            "auth": "/api/v1/auth/login",
            "agents": "/api/v1/agents",
            "metrics": "/api/v1/metrics",
            "events": "/api/v1/events",
            "clusters": "/api/v1/clusters",
            "rules": "/api/v1/rules",
            "audit": "/api/v1/audit",
            "websocket": "/ws/dashboard",
        },
    }


# ─── Auth Routes ───

@app.post("/api/v1/auth/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user["id"], user["username"], user.get("role", "admin"))

    # Audit log
    ip = request.client.host if request.client else ""
    insert_audit_log(user["id"], user["username"], "login", "auth", {"method": "password"}, ip)

    return {"token": token, "user": {"id": user["id"], "username": user["username"], "role": user.get("role", "admin")}}


@app.get("/api/v1/auth/me")
async def get_me(user: dict = Depends(require_auth)):
    full_user = get_user_by_id(user["id"])
    if not full_user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": full_user["id"], "username": full_user["username"], "role": full_user.get("role", "admin")}


# ─── Cluster Routes ───

@app.get("/api/v1/clusters")
async def get_all_clusters():
    clusters = list_clusters()
    return {"clusters": clusters, "total": len(clusters)}


@app.post("/api/v1/clusters")
async def create_new_cluster(request: Request, user: dict = Depends(require_auth)):
    body = await request.json()
    cluster = create_cluster(body.get("name", ""), body.get("description", ""))
    insert_audit_log(user["id"], user["username"], "create_cluster", f"cluster:{cluster['id']}", body)
    return {"status": "created", "cluster": cluster}


# ─── Agent Routes ───

@app.post("/api/v1/agents/register")
async def register_new_agent(request: Request):
    body = await request.json()
    agent = register_agent(
        name=body.get("name", "unnamed"),
        agent_type=body.get("agent_type", "unknown"),
        hostname=body.get("hostname", ""),
        labels=body.get("labels", {}),
        cluster_id=body.get("cluster_id", "default"),
    )
    logger.info(f"Agent registered: {agent['name']} ({agent['agent_type']})")
    return {"status": "registered", "agent": agent}


@app.get("/api/v1/agents")
async def get_all_agents(cluster_id: str = Query(None)):
    agents = list_agents(cluster_id=cluster_id)
    return {"agents": agents, "total": len(agents)}


@app.get("/api/v1/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.post("/api/v1/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str):
    update_agent_heartbeat(agent_id)
    return {"status": "ok"}


# ─── Metrics Routes ───

@app.post("/api/v1/metrics")
async def receive_metrics(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id", "")
    agent_type = body.get("agent_type", "unknown")
    hostname = body.get("hostname", "")
    cluster_id = body.get("cluster_id", "default")

    get_or_create_agent(agent_id, body.get("agent_name", agent_id), agent_type, hostname, cluster_id)

    metrics = body.get("metrics", [])
    if metrics:
        insert_metrics(agent_id, metrics)
        logger.info(f"Received {len(metrics)} metrics from agent {agent_id}")

    await check_metric_alerts(agent_id, metrics)

    # WebSocket broadcast
    await ws_manager.broadcast({"type": "metrics", "agent_id": agent_id, "count": len(metrics)})

    return {"status": "ok", "received": len(metrics)}


@app.get("/api/v1/metrics")
async def query_metrics(
    agent_id: str = Query(None), metric_name: str = Query(None),
    last_hours: int = Query(24), limit: int = Query(1000),
):
    data = get_metrics(agent_id=agent_id, metric_name=metric_name, last_hours=last_hours, limit=limit)
    return {"metrics": data, "total": len(data)}


# ─── Chart Routes ───

@app.get("/api/v1/charts/metrics")
async def chart_metrics(
    agent_id: str = Query(None), last_hours: int = Query(6), metric_names: str = Query(None),
):
    names = metric_names.split(",") if metric_names else None
    data = get_metrics_timeseries(agent_id=agent_id, last_hours=last_hours, metric_names=names)
    return {"timeseries": data, "points": len(data)}


@app.get("/api/v1/charts/events")
async def chart_events(last_hours: int = Query(24)):
    data = get_event_counts_by_hour(last_hours=last_hours)
    return {"timeseries": data, "hours": len(data)}


# ─── Events Routes ───

@app.post("/api/v1/events")
async def receive_events(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id", "")
    agent_type = body.get("agent_type", "unknown")
    hostname = body.get("hostname", "")

    get_or_create_agent(agent_id, body.get("agent_name", agent_id), agent_type, hostname)

    events = body.get("events", [])
    if events:
        insert_events(agent_id, events)
        logger.info(f"Received {len(events)} events from agent {agent_id}")

        for event in events:
            level = event.get("level", "info")
            if level in ("error", "critical"):
                await trigger_alert(event)

        # WebSocket broadcast
        await ws_manager.broadcast({
            "type": "events", "agent_id": agent_id, "count": len(events),
            "events": [{"title": e.get("title",""), "level": e.get("level","info")} for e in events[:5]]
        })

    return {"status": "ok", "received": len(events)}


@app.get("/api/v1/events")
async def query_events(
    agent_id: str = Query(None), level: str = Query(None),
    last_hours: int = Query(24), limit: int = Query(200),
):
    data = get_events(agent_id=agent_id, level=level, last_hours=last_hours, limit=limit)
    return {"events": data, "total": len(data)}


@app.post("/api/v1/events/{event_id}/acknowledge")
async def ack_event(event_id: str):
    acknowledge_event(event_id)
    return {"status": "acknowledged"}


# ─── Logs Routes ───

@app.post("/api/v1/logs")
async def receive_logs(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id", "")
    get_or_create_agent(agent_id, body.get("agent_name", agent_id), body.get("agent_type", "unknown"))

    logs = body.get("logs", [])
    if logs:
        insert_logs(agent_id, logs)
        logger.info(f"Received {len(logs)} log entries from agent {agent_id}")

        error_logs = [l for l in logs if l.get("log_level") == "error"]
        if error_logs:
            await trigger_log_alert(agent_id, error_logs)

    return {"status": "ok", "received": len(logs)}


@app.get("/api/v1/logs")
async def query_logs(
    agent_id: str = Query(None), last_hours: int = Query(24), limit: int = Query(500),
):
    data = get_logs(agent_id=agent_id, last_hours=last_hours, limit=limit)
    return {"logs": data, "total": len(data)}


# ─── Dashboard ───

@app.get("/api/v1/dashboard/summary")
async def dashboard_summary(cluster_id: str = Query(None)):
    agents = list_agents(cluster_id=cluster_id)
    event_counts = get_event_counts(last_hours=24)
    latest_metrics = get_latest_metrics_per_agent()
    recent_events = get_events(last_hours=24, limit=50)

    return {
        "summary": {
            "total_agents": len(agents),
            "active_agents": sum(1 for a in agents if a.get("status") == "active"),
            "total_events_24h": sum(event_counts.values()),
            "critical_alerts": event_counts.get("critical", 0),
            "error_alerts": event_counts.get("error", 0),
            "warning_alerts": event_counts.get("warning", 0),
        },
        "agents": agents,
        "latest_metrics": latest_metrics,
        "recent_events": recent_events[:20],
    }


# ─── Alert Config Routes ───

@app.get("/api/v1/settings/alerts")
async def get_alert_settings():
    return {"configs": get_alert_configs()}


@app.post("/api/v1/settings/alerts")
async def create_alert_setting(request: Request):
    body = await request.json()
    config = save_alert_config(
        channel=body.get("channel", "telegram"),
        config=body.get("config", {}),
        enabled=body.get("enabled", True),
        alert_levels=body.get("alert_levels", ["critical", "error"]),
    )
    return {"status": "created", "config": config}


@app.delete("/api/v1/settings/alerts/{config_id}")
async def remove_alert_setting(config_id: str):
    delete_alert_config(config_id)
    return {"status": "deleted"}


# ─── Notification Rules Routes ───

@app.get("/api/v1/rules")
async def list_rules():
    rules = get_rules()
    return {"rules": rules, "total": len(rules)}


@app.post("/api/v1/rules")
async def create_rule(request: Request):
    body = await request.json()
    rule = save_rule(
        name=body.get("name", ""),
        metric_name=body.get("metric_name", "cpu_percent"),
        operator=body.get("operator", ">"),
        threshold=body.get("threshold", 90),
        duration_minutes=body.get("duration_minutes", 5),
        channels=body.get("channels", ["telegram"]),
    )
    return {"status": "created", "rule": rule}


@app.delete("/api/v1/rules/{rule_id}")
async def remove_rule(rule_id: str):
    delete_rule(rule_id)
    return {"status": "deleted"}


@app.put("/api/v1/rules/{rule_id}/toggle")
async def toggle_rule_endpoint(rule_id: str, request: Request):
    body = await request.json()
    toggle_rule(rule_id, body.get("enabled", True))
    return {"status": "updated"}


# ─── Report Routes ───

@app.post("/api/v1/reports/generate")
async def generate_and_send_report(request: Request):
    body = await request.json()
    channels = body.get("channels", ["telegram"])

    from report_service.reports import generate_report, format_report_telegram, format_report_email

    agents = list_agents()
    metrics_by_agent = get_latest_metrics_per_agent()
    events = get_events(last_hours=24)
    logs = get_logs(last_hours=24)

    report = generate_report(agents, metrics_by_agent, events, logs, "on_demand")

    sent_to = []
    configs = get_alert_configs()

    for channel in channels:
        channel_configs = [c for c in configs if c["channel"] == channel and c.get("enabled")]
        for cfg in channel_configs:
            channel_config = cfg.get("config", {})
            try:
                if channel == "telegram":
                    from alert_service.providers import TelegramProvider
                    provider = TelegramProvider(
                        bot_token=channel_config.get("bot_token", ""),
                        chat_id=channel_config.get("chat_id", ""),
                    )
                    text = format_report_telegram(report)
                    if await provider.send(text):
                        sent_to.append("telegram")
                elif channel == "email":
                    from alert_service.providers import EmailProvider
                    provider = EmailProvider(
                        smtp_host=channel_config.get("smtp_host", ""),
                        smtp_port=channel_config.get("smtp_port", 587),
                        username=channel_config.get("username", ""),
                        password=channel_config.get("password", ""),
                        from_addr=channel_config.get("from_addr", ""),
                        to_addrs=channel_config.get("to_addrs", []),
                    )
                    text = format_report_email(report)
                    if await provider.send("Insight Daily Report", text):
                        sent_to.append("email")
            except Exception as e:
                logger.error(f"Report send to {channel} failed: {e}")

    saved = save_report("on_demand", report, sent_to)
    return {"status": "generated", "report": saved, "sent_to": sent_to}


@app.get("/api/v1/reports")
async def list_reports(limit: int = Query(20)):
    return {"reports": get_reports(limit=limit)}


# ─── Settings Routes ───

@app.get("/api/v1/settings")
async def get_system_settings():
    auto_report = get_setting("auto_report", {
        "enabled": False, "schedule": "45 0 * * *",
        "channels": ["telegram"], "timezone": "Asia/Ho_Chi_Minh",
    })
    return {
        "auto_report": auto_report,
        "alert_dedup_minutes": get_setting("alert_dedup_minutes", 5),
        "metric_retention_days": get_setting("metric_retention_days", 30),
    }


@app.put("/api/v1/settings")
async def update_system_settings(request: Request):
    body = await request.json()
    for key, value in body.items():
        set_setting(key, value)
    return {"status": "updated"}


# ─── Audit Routes ───

@app.get("/api/v1/audit")
async def get_audit(last_hours: int = Query(168), limit: int = Query(100)):
    logs = get_audit_logs(last_hours=last_hours, limit=limit)
    return {"logs": logs, "total": len(logs)}


# ─── WebSocket ───

@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send ping, we respond with pong
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ─── Internal Alert Logic ───

async def trigger_alert(event: dict):
    try:
        from alert_service.providers import alert_manager
        configs = get_alert_configs()
        await alert_manager.send_alert(
            level=event.get("level", "error"),
            title=event.get("title", ""),
            message=event.get("message", ""),
            source=event.get("source", ""),
            configs=configs,
        )
    except Exception as e:
        logger.error(f"Alert trigger failed: {e}")


async def trigger_log_alert(agent_id: str, error_logs: list[dict]):
    try:
        from alert_service.providers import alert_manager
        configs = get_alert_configs()
        summary = f"Detected {len(error_logs)} error logs"
        details = "\n".join(
            f"[{l.get('namespace', '')}] {l.get('pod_name', '')}: {l.get('message', '')[:100]}"
            for l in error_logs[:5]
        )
        await alert_manager.send_alert(level="error", title=summary, message=details,
                                       source=f"agent:{agent_id}", configs=configs)
    except Exception as e:
        logger.error(f"Log alert trigger failed: {e}")


async def check_metric_alerts(agent_id: str, metrics: list[dict]):
    # Check notification rules
    rules = get_rules(enabled_only=True)
    for m in metrics:
        name = m.get("metric_name", "")
        value = m.get("metric_value", 0)

        for rule in rules:
            if rule["metric_name"] != name:
                continue
            op = rule["operator"]
            threshold = rule["threshold"]
            triggered = False
            if op == ">" and value > threshold: triggered = True
            elif op == ">=" and value >= threshold: triggered = True
            elif op == "<" and value < threshold: triggered = True
            elif op == "<=" and value <= threshold: triggered = True
            elif op == "==" and value == threshold: triggered = True

            if triggered:
                try:
                    from alert_service.providers import alert_manager
                    configs = get_alert_configs()
                    await alert_manager.send_alert(
                        level="critical" if value > threshold + 5 else "warning",
                        title=f"Rule: {rule['name']} triggered",
                        message=f"Agent {agent_id}: {name} = {value:.1f} ({op} {threshold})",
                        source=f"rule:{rule['id']}",
                        configs=configs,
                    )
                except Exception as e:
                    logger.error(f"Rule alert failed: {e}")

    # Legacy threshold check (fallback)
    thresholds = get_setting("metric_thresholds", {
        "cpu_percent": 90, "memory_percent": 90, "disk_percent": 95,
    })
    for m in metrics:
        name = m.get("metric_name", "")
        value = m.get("metric_value", 0)
        if name in thresholds and value > thresholds[name]:
            try:
                from alert_service.providers import alert_manager
                configs = get_alert_configs()
                await alert_manager.send_alert(
                    level="critical" if value > thresholds[name] + 5 else "error",
                    title=f"{name} high: {value:.1f}%",
                    message=f"Agent {agent_id}: {name} = {value:.1f}% (threshold: {thresholds[name]}%)",
                    source=f"agent:{agent_id}", configs=configs,
                )
            except Exception as e:
                logger.error(f"Metric alert failed: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
