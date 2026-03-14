"""
Insight Monitoring System - API Gateway v6.0.0
Dashboard-facing service: Auth, queries, config CRUD, K8s proxy, AI chat, WebSocket.
Data ingestion moved to Data Collector service.
Alert processing moved to Alert Worker service.
"""

import asyncio
import time as _time
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.db import (
    init_db, list_agents, get_agent,
    get_metrics, get_latest_metrics_per_agent,
    get_metrics_timeseries, get_event_counts_by_hour,
    get_events, get_event_counts, acknowledge_event,
    get_logs,
    save_alert_config, get_alert_configs, delete_alert_config,
    save_report, get_reports, get_setting, set_setting,
    create_user, get_user_by_username, get_user_by_id, list_users, update_user_password, delete_user,
    create_cluster, list_clusters, get_cluster,
    save_rule, get_rules, delete_rule, toggle_rule,
    insert_audit_log, get_audit_logs,
    save_webhook, get_webhooks, delete_webhook, toggle_webhook,
    get_process_snapshot,
    get_traces, get_trace_summary,
    get_storage_stats, apply_retention_policies, purge_all_data,
    get_services, get_traces_by_service, get_metrics_by_service,
    create_agent_token, list_agent_tokens, revoke_agent_token,
    get_agents_by_token, migrate_agent_tokens_table,
)
from api_gateway.auth import (
    hash_password, verify_password, create_token, verify_token,
    ensure_default_admin, get_current_user, require_auth, require_role,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("insight.gateway")

# ─── WebSocket Manager ───
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)
        logger.info(f"WS connected ({len(self.active_connections)} total)")
    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections: self.active_connections.remove(ws)
        logger.info(f"WS disconnected ({len(self.active_connections)} total)")
    async def broadcast(self, msg: dict):
        dead = []
        for c in self.active_connections:
            try: await c.send_json(msg)
            except: dead.append(c)
        for d in dead: self.disconnect(d)

ws_manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Insight API Gateway v6.0.0 starting...")
    init_db()
    migrate_agent_tokens_table()
    ensure_default_admin()
    logger.info("Database and auth initialized")
    yield
    logger.info("Shutting down")

app = FastAPI(title="Insight Monitoring System", version="6.0.0", lifespan=lifespan)

# ─── CORS (restrict to specific origins) ───
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Note: Agent ingestion auth (API key + agent token) is in Data Collector service

# ─── Response time logging middleware ───
@app.middleware("http")
async def log_response_time(request: Request, call_next):
    start = _time.monotonic()
    response = await call_next(request)
    elapsed_ms = round((_time.monotonic() - start) * 1000, 1)
    path = request.url.path
    if path != "/health":
        print(f"[PERF] {request.method} {path} => {response.status_code} ({elapsed_ms}ms)", flush=True)
    return response

# ─── Request size limit middleware (10MB) ───
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": "Request body too large (max 10MB)"})
    return await call_next(request)

# ─── Login rate limiting (in-memory) ───
_login_attempts: dict[str, list[float]] = {}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60

# ─── Health ───
@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway", "version": "6.0.0", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/")
async def root():
    return {"app": "Insight Monitoring System", "service": "api-gateway", "version": "6.0.0"}

# ════════════════════════════════════════════════
# AUTH ROUTES
# ════════════════════════════════════════════════

@app.post("/api/v1/auth/login")
async def login(request: Request):
    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc).timestamp()
    attempts = _login_attempts.get(client_ip, [])
    attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    body = await request.json()
    username, password = body.get("username", ""), body.get("password", "")
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    user = get_user_by_username(username)
    if not user or not verify_password(body.get("password", ""), user["password_hash"]):
        _login_attempts.setdefault(client_ip, []).append(now)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _login_attempts.pop(client_ip, None)  # Clear on success
    token = create_token(user["id"], user["username"], user.get("role", "viewer"))
    ip = request.client.host if request.client else ""
    insert_audit_log(user["id"], user["username"], "login", "auth", {"method": "password"}, ip)
    return {"token": token, "user": {"id": user["id"], "username": user["username"], "role": user.get("role", "admin")}}

@app.get("/api/v1/auth/me")
async def get_me(user: dict = Depends(require_auth)):
    full = get_user_by_id(user["id"])
    if not full: raise HTTPException(404, "User not found")
    return {"id": full["id"], "username": full["username"], "role": full.get("role", "admin")}

@app.put("/api/v1/auth/password")
async def change_password(request: Request, user: dict = Depends(require_auth)):
    body = await request.json()
    current_pw, new_pw = body.get("current_password", ""), body.get("new_password", "")
    if not current_pw or not new_pw:
        raise HTTPException(400, "Current and new passwords required")
    if len(new_pw) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    full = get_user_by_id(user["id"])
    if not full or not verify_password(current_pw, full["password_hash"]):
        raise HTTPException(401, "Current password incorrect")
    update_user_password(user["id"], hash_password(new_pw))
    ip = request.client.host if request.client else ""
    insert_audit_log(user["id"], user["username"], "change_password", "auth", {}, ip)
    return {"status": "password_changed"}

# ════════════════════════════════════════════════
# USER MANAGEMENT (admin only)
# ════════════════════════════════════════════════

@app.get("/api/v1/users")
async def get_all_users(user: dict = Depends(require_role(["admin"]))):
    users = list_users()
    return {"users": users, "total": len(users)}

@app.post("/api/v1/users")
async def create_new_user(request: Request, user: dict = Depends(require_role(["admin"]))):
    body = await request.json()
    username, password, role = body.get("username",""), body.get("password",""), body.get("role","viewer")
    if not username or not password: raise HTTPException(400, "Username and password required")
    if role not in ("admin","operator","viewer"): raise HTTPException(400, "Invalid role")
    existing = get_user_by_username(username)
    if existing: raise HTTPException(409, "Username already exists")
    pw_hash = hash_password(password)
    new_user = create_user(username, pw_hash, role)
    insert_audit_log(user["id"], user["username"], "create_user", f"user:{new_user['id']}", {"target": username, "role": role})
    return {"status": "created", "user": new_user}

@app.delete("/api/v1/users/{user_id}")
async def remove_user(user_id: str, user: dict = Depends(require_role(["admin"]))):
    if user_id == user["id"]: raise HTTPException(400, "Cannot delete yourself")
    target = get_user_by_id(user_id)
    if not target: raise HTTPException(404, "User not found")
    delete_user(user_id)
    insert_audit_log(user["id"], user["username"], "delete_user", f"user:{user_id}", {"target": target.get("username","")})
    return {"status": "deleted"}

# ════════════════════════════════════════════════
# CLUSTER ROUTES
# ════════════════════════════════════════════════

@app.get("/api/v1/clusters")
async def get_all_clusters():
    clusters = list_clusters()
    return {"clusters": clusters, "total": len(clusters)}

@app.post("/api/v1/clusters")
async def create_new_cluster(request: Request, user: dict = Depends(require_role(["admin"]))):
    body = await request.json()
    cluster = create_cluster(body.get("name",""), body.get("description",""))
    insert_audit_log(user["id"], user["username"], "create_cluster", f"cluster:{cluster['id']}", body)
    return {"status": "created", "cluster": cluster}

# ════════════════════════════════════════════════
# AGENT ROUTES (read-only — registration/heartbeat in Data Collector)
# ════════════════════════════════════════════════

@app.get("/api/v1/agents")
async def get_all_agents(cluster_id: str = Query(None), category: str = Query(None),
                        from_time: str = Query(None), to_time: str = Query(None)):
    agents = list_agents(cluster_id=cluster_id, from_time=from_time, to_time=to_time)
    if category and category != 'all':
        agents = [a for a in agents if a.get('agent_category') == category]
    metrics_map = get_latest_metrics_per_agent()
    for a in agents:
        a["latest_metrics"] = metrics_map.get(a["id"], [])
    return {"agents": agents, "total": len(agents)}

@app.get("/api/v1/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    agent = get_agent(agent_id)
    if not agent: raise HTTPException(404, "Agent not found")
    return agent

@app.delete("/api/v1/agents/{agent_id}")
async def delete_agent_endpoint(agent_id: str, user: dict = Depends(require_role(["admin"]))):
    """Delete an agent by ID (admin only)."""
    from shared.database.db import delete_agent
    delete_agent(agent_id)
    insert_audit_log(user["id"], user["username"], "delete_agent", "agent", {"agent_id": agent_id})
    return {"status": "deleted", "agent_id": agent_id}

# ════════════════════════════════════════════════
# AGENT TOKEN MANAGEMENT
# ════════════════════════════════════════════════

@app.post("/api/v1/agent-tokens")
async def create_token_endpoint(request: Request, user: dict = Depends(require_role(["admin"]))):
    body = await request.json()
    name = body.get("name", "")
    if not name:
        raise HTTPException(400, "Token name is required")
    token = create_agent_token(
        name=name,
        agent_type=body.get("agent_type", "any"),
        cluster_id=body.get("cluster_id", "default"),
        created_by=user.get("username", ""),
    )
    insert_audit_log(user["id"], user["username"], "create_agent_token", f"token:{token['id']}", {"name": name})
    return {"status": "created", "token": token}

@app.get("/api/v1/agent-tokens")
async def list_tokens_endpoint(user: dict = Depends(require_role(["admin"]))):
    tokens = list_agent_tokens()
    # Mask token values for security (show only first 8 chars)
    for t in tokens:
        if t.get("token"):
            t["token_preview"] = t["token"][:12] + "..."
            del t["token"]  # Don't expose full token in list
    return {"tokens": tokens, "total": len(tokens)}

@app.delete("/api/v1/agent-tokens/{token_id}")
async def revoke_token_endpoint(token_id: str, user: dict = Depends(require_role(["admin"]))):
    revoke_agent_token(token_id)
    insert_audit_log(user["id"], user["username"], "revoke_agent_token", f"token:{token_id}", {})
    return {"status": "revoked"}

@app.get("/api/v1/agent-tokens/{token_id}/agents")
async def get_token_agents(token_id: str, user: dict = Depends(require_role(["admin"]))):
    agents = get_agents_by_token(token_id)
    return {"agents": agents, "total": len(agents)}

# ════════════════════════════════════════════════
# METRICS ROUTES (read-only — ingestion in Data Collector)
# ════════════════════════════════════════════════

@app.get("/api/v1/metrics")
async def query_metrics(agent_id: str = Query(None), metric_name: str = Query(None),
                        last_hours: int = Query(24), limit: int = Query(1000),
                        from_time: str = Query(None), to_time: str = Query(None)):
    data = get_metrics(agent_id=agent_id, metric_name=metric_name, last_hours=last_hours, limit=limit,
                       from_time=from_time, to_time=to_time)
    return {"metrics": data, "total": len(data)}

# ════════════════════════════════════════════════
# CHART ROUTES
# ════════════════════════════════════════════════

@app.get("/api/v1/charts/metrics")
async def chart_metrics(agent_id: str = Query(None), last_hours: int = Query(6), metric_names: str = Query(None)):
    names = metric_names.split(",") if metric_names else None
    data = get_metrics_timeseries(agent_id=agent_id, last_hours=last_hours, metric_names=names)
    return {"timeseries": data, "points": len(data)}

@app.get("/api/v1/charts/events")
async def chart_events(last_hours: int = Query(24)):
    return {"timeseries": get_event_counts_by_hour(last_hours=last_hours)}

# ════════════════════════════════════════════════
# EVENTS ROUTES (read-only — ingestion in Data Collector)
# ════════════════════════════════════════════════

@app.get("/api/v1/events")
async def query_events(agent_id: str = Query(None), level: str = Query(None),
                       last_hours: int = Query(24), limit: int = Query(200),
                       from_time: str = Query(None), to_time: str = Query(None)):
    data = get_events(agent_id=agent_id, level=level, last_hours=last_hours, limit=limit,
                      from_time=from_time, to_time=to_time)
    return {"events": data, "total": len(data)}

@app.post("/api/v1/events/{event_id}/acknowledge", dependencies=[Depends(require_auth)])
async def ack_event(event_id: str):
    acknowledge_event(event_id)
    return {"status": "acknowledged"}

# ════════════════════════════════════════════════
# LOGS ROUTES (read-only — ingestion in Data Collector)
# ════════════════════════════════════════════════

@app.get("/api/v1/logs")
async def query_logs(agent_id: str = Query(None), last_hours: int = Query(24), limit: int = Query(500),
                     from_time: str = Query(None), to_time: str = Query(None)):
    return {"logs": get_logs(agent_id=agent_id, last_hours=last_hours, limit=limit,
                             from_time=from_time, to_time=to_time)}

# ════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════

@app.get("/api/v1/dashboard/summary")
async def dashboard_summary(cluster_id: str = Query(None), from_time: str = Query(None), to_time: str = Query(None)):
    agents = list_agents(cluster_id=cluster_id, from_time=from_time, to_time=to_time)
    last_hours = 24  # default for event counts
    event_counts = get_event_counts(last_hours=last_hours)
    latest_metrics = get_latest_metrics_per_agent()
    recent_events = get_events(last_hours=last_hours, limit=50, from_time=from_time, to_time=to_time)
    clusters = list_clusters()
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
        "clusters": clusters,
    }

# ════════════════════════════════════════════════
# ALERT CONFIG
# ════════════════════════════════════════════════

@app.get("/api/v1/settings/alerts", dependencies=[Depends(require_auth)])
async def get_alert_settings():
    return {"configs": get_alert_configs()}

@app.post("/api/v1/settings/alerts")
async def create_alert_setting(request: Request, user: dict = Depends(require_role(["admin","operator"]))):
    body = await request.json()
    config = save_alert_config(channel=body.get("channel","telegram"), config=body.get("config",{}),
                               enabled=body.get("enabled",True), alert_levels=body.get("alert_levels",["critical","error"]))
    insert_audit_log(user["id"], user["username"], "create_alert", f"alert:{config['id']}", body)
    return {"status": "created", "config": config}

@app.delete("/api/v1/settings/alerts/{config_id}")
async def remove_alert_setting(config_id: str, user: dict = Depends(require_role(["admin"]))):
    delete_alert_config(config_id)
    return {"status": "deleted"}

# ════════════════════════════════════════════════
# WEBHOOK ROUTES
# ════════════════════════════════════════════════

@app.get("/api/v1/webhooks", dependencies=[Depends(require_auth)])
async def list_all_webhooks():
    wh = get_webhooks()
    return {"webhooks": wh, "total": len(wh)}

@app.post("/api/v1/webhooks")
async def create_webhook(request: Request, user: dict = Depends(require_role(["admin","operator"]))):
    body = await request.json()
    wh = save_webhook(name=body.get("name",""), url=body.get("url",""), wh_type=body.get("type","custom"),
                      events=body.get("events", ["critical","error"]))
    insert_audit_log(user["id"], user["username"], "create_webhook", f"webhook:{wh['id']}", {"name": wh["name"]})
    return {"status": "created", "webhook": wh}

@app.delete("/api/v1/webhooks/{wh_id}")
async def remove_webhook(wh_id: str, user: dict = Depends(require_role(["admin"]))):
    delete_webhook(wh_id)
    return {"status": "deleted"}

@app.put("/api/v1/webhooks/{wh_id}/toggle")
async def toggle_wh(wh_id: str, request: Request, user: dict = Depends(require_role(["admin","operator"]))):
    body = await request.json()
    toggle_webhook(wh_id, body.get("enabled", True))
    return {"status": "updated"}

@app.post("/api/v1/webhooks/{wh_id}/test")
async def test_webhook(wh_id: str, user: dict = Depends(require_role(["admin","operator"]))):
    webhooks = get_webhooks()
    wh = next((w for w in webhooks if w["id"] == wh_id), None)
    if not wh: raise HTTPException(404, "Webhook not found")
    from api_gateway.webhook_sender import send_slack, send_discord, send_custom
    ok = False
    if wh["type"] == "slack": ok = await send_slack(wh["url"], "info", "Test Alert", "This is a test from Insight", "test")
    elif wh["type"] == "discord": ok = await send_discord(wh["url"], "info", "Test Alert", "This is a test from Insight", "test")
    else: ok = await send_custom(wh["url"], "info", "Test Alert", "This is a test from Insight", "test")
    return {"status": "sent" if ok else "failed", "ok": ok}

# ════════════════════════════════════════════════
# NOTIFICATION RULES
# ════════════════════════════════════════════════

@app.get("/api/v1/rules", dependencies=[Depends(require_auth)])
async def list_rules():
    rules = get_rules()
    return {"rules": rules, "total": len(rules)}

@app.post("/api/v1/rules")
async def create_rule(request: Request, user: dict = Depends(require_role(["admin","operator"]))):
    body = await request.json()
    rule = save_rule(name=body.get("name",""), metric_name=body.get("metric_name","cpu_percent"),
                     operator=body.get("operator",">"), threshold=body.get("threshold",90),
                     duration_minutes=body.get("duration_minutes",5), channels=body.get("channels",["telegram"]))
    insert_audit_log(user["id"], user["username"], "create_rule", f"rule:{rule['id']}", body)
    return {"status": "created", "rule": rule}

@app.delete("/api/v1/rules/{rule_id}")
async def remove_rule(rule_id: str, user: dict = Depends(require_role(["admin"]))):
    delete_rule(rule_id)
    return {"status": "deleted"}

@app.put("/api/v1/rules/{rule_id}/toggle")
async def toggle_rule_ep(rule_id: str, request: Request):
    body = await request.json()
    toggle_rule(rule_id, body.get("enabled", True))
    return {"status": "updated"}

# ════════════════════════════════════════════════
# REPORTS
# ════════════════════════════════════════════════

@app.post("/api/v1/reports/generate")
async def generate_and_send_report(request: Request, user: dict = Depends(require_role(["admin","operator"]))):
    body = await request.json()
    channels = body.get("channels", ["telegram"])
    from report_service.reports import generate_report, format_report_telegram
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
            cc = cfg.get("config", {})
            try:
                if channel == "telegram":
                    from alert_service.providers import TelegramProvider
                    provider = TelegramProvider(bot_token=cc.get("bot_token",""), chat_id=cc.get("chat_id",""))
                    if await provider.send(format_report_telegram(report)): sent_to.append("telegram")
            except Exception as e: logger.error(f"Report send failed: {e}")
    saved = save_report("on_demand", report, sent_to)
    insert_audit_log(user["id"], user["username"], "generate_report", "report", {"sent_to": sent_to})
    return {"status": "generated", "report": saved, "sent_to": sent_to}

@app.get("/api/v1/reports")
async def list_reports(limit: int = Query(20)):
    return {"reports": get_reports(limit=limit)}

# ════════════════════════════════════════════════
# SETTINGS
# ════════════════════════════════════════════════

@app.get("/api/v1/settings")
async def get_system_settings():
    return {
        "auto_report": get_setting("auto_report", {"enabled": False, "schedule": "45 0 * * *", "channels": ["telegram"]}),
        "alert_dedup_minutes": get_setting("alert_dedup_minutes", 5),
        "metric_retention_days": get_setting("metric_retention_days", 30),
    }

@app.put("/api/v1/settings")
async def update_system_settings(request: Request, user: dict = Depends(require_role(["admin"]))):
    body = await request.json()
    for key, value in body.items(): set_setting(key, value)
    insert_audit_log(user["id"], user["username"], "update_settings", "settings", body)
    return {"status": "updated"}

# ════════════════════════════════════════════════
# AUDIT LOG
# ════════════════════════════════════════════════

@app.get("/api/v1/audit")
async def get_audit(last_hours: int = Query(168), limit: int = Query(100), user: dict = Depends(require_role(["admin"]))):
    logs = get_audit_logs(last_hours=last_hours, limit=limit)
    return {"logs": logs, "total": len(logs)}

# ════════════════════════════════════════════════
# WEBSOCKET
# ════════════════════════════════════════════════

@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    # Max connections limit
    if len(ws_manager.active_connections) >= 50:
        await websocket.close(code=1013)
        return
    # Auth: require valid token in query param
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=4001)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping": await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# Alert logic and process ingestion moved to Alert Worker and Data Collector services

@app.get("/api/v1/processes", dependencies=[Depends(require_auth)])
async def query_processes(agent_id: str = None):
    if not agent_id:
        raise HTTPException(400, "agent_id required")
    result = get_process_snapshot(agent_id)
    return result

# Trace ingestion moved to Data Collector service

@app.get("/api/v1/traces", dependencies=[Depends(require_auth)])
async def query_traces(agent_id: str = None, last_hours: int = 24, limit: int = 100,
                       from_time: str = Query(None), to_time: str = Query(None)):
    result = get_traces(agent_id=agent_id, last_hours=last_hours, limit=limit,
                        from_time=from_time, to_time=to_time)
    return {"traces": result, "total": len(result)}

@app.get("/api/v1/traces/summary", dependencies=[Depends(require_auth)])
async def trace_summary(last_hours: int = 1):
    """Aggregate trace stats for Application Monitoring dashboard."""
    return get_trace_summary(last_hours=last_hours)

# ─── Services (v5.0.2) ───

@app.get("/api/v1/services", dependencies=[Depends(require_auth)])
async def list_services(last_hours: int = Query(24)):
    """Get distinct OTel service names from traces."""
    services = get_services(last_hours=last_hours)
    return {"services": services, "total": len(services)}

@app.get("/api/v1/services/{service_name}/traces")
async def service_traces(service_name: str, last_hours: int = Query(24), limit: int = Query(100)):
    """Get traces for a specific service."""
    traces = get_traces_by_service(service_name, last_hours=last_hours, limit=limit)
    return {"traces": traces, "total": len(traces), "service": service_name}

@app.get("/api/v1/services/{service_name}/metrics")
async def service_metrics(service_name: str, last_hours: int = Query(24), limit: int = Query(500)):
    """Get metrics for a specific service."""
    metrics = get_metrics_by_service(service_name, last_hours=last_hours, limit=limit)
    return {"metrics": metrics, "total": len(metrics), "service": service_name}

# OTLP receivers moved to Data Collector service


@app.get("/api/v1/storage/stats", dependencies=[Depends(require_auth)])
async def storage_stats():
    """Get storage statistics per table."""
    return get_storage_stats()

@app.post("/api/v1/retention/apply", dependencies=[Depends(require_auth)])
async def retention_apply():
    """Apply retention policies from settings to ClickHouse TTL."""
    result = apply_retention_policies()
    return result

@app.post("/api/v1/storage/purge")
async def storage_purge(user=Depends(get_current_user)):
    """Purge all time-series data (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Only admin users can purge data")
    result = purge_all_data()
    insert_audit_log(user_id=user.get("id", "system"), username=user.get("username", "system"),
                     action="purge_all_data", resource="storage", details=result)
    return result

# ════════════════════════════════════════════════
# K8S RESOURCE BROWSING (Real-time K8s API)
# ════════════════════════════════════════════════

@app.get("/api/v1/k8s/nodes", dependencies=[Depends(require_auth)])
async def k8s_nodes():
    from api_gateway.k8s_resources import get_k8s_nodes
    return {"nodes": get_k8s_nodes()}

@app.get("/api/v1/k8s/namespaces", dependencies=[Depends(require_auth)])
async def k8s_namespaces():
    from api_gateway.k8s_resources import get_k8s_namespaces
    return {"namespaces": get_k8s_namespaces()}

@app.get("/api/v1/k8s/namespaces/{ns}/pods", dependencies=[Depends(require_auth)])
async def k8s_pods(ns: str):
    from api_gateway.k8s_resources import get_k8s_pods
    ns_param = None if ns == "_all" else ns
    return {"pods": get_k8s_pods(ns_param)}

@app.get("/api/v1/k8s/namespaces/{ns}/deployments", dependencies=[Depends(require_auth)])
async def k8s_deployments(ns: str):
    from api_gateway.k8s_resources import get_k8s_deployments
    ns_param = None if ns == "_all" else ns
    return {"deployments": get_k8s_deployments(ns_param)}

@app.get("/api/v1/k8s/namespaces/{ns}/statefulsets", dependencies=[Depends(require_auth)])
async def k8s_statefulsets(ns: str):
    from api_gateway.k8s_resources import get_k8s_statefulsets
    ns_param = None if ns == "_all" else ns
    return {"statefulsets": get_k8s_statefulsets(ns_param)}

@app.get("/api/v1/k8s/namespaces/{ns}/daemonsets", dependencies=[Depends(require_auth)])
async def k8s_daemonsets(ns: str):
    from api_gateway.k8s_resources import get_k8s_daemonsets
    ns_param = None if ns == "_all" else ns
    return {"daemonsets": get_k8s_daemonsets(ns_param)}

@app.get("/api/v1/k8s/namespaces/{ns}/services", dependencies=[Depends(require_auth)])
async def k8s_services(ns: str):
    from api_gateway.k8s_resources import get_k8s_services
    ns_param = None if ns == "_all" else ns
    return {"services": get_k8s_services(ns_param)}

@app.get("/api/v1/k8s/namespaces/{ns}/configmaps", dependencies=[Depends(require_auth)])
async def k8s_configmaps(ns: str):
    from api_gateway.k8s_resources import get_k8s_configmaps
    ns_param = None if ns == "_all" else ns
    return {"configmaps": get_k8s_configmaps(ns_param)}

@app.get("/api/v1/k8s/namespaces/{ns}/secrets", dependencies=[Depends(require_auth)])
async def k8s_secrets(ns: str):
    from api_gateway.k8s_resources import get_k8s_secrets
    ns_param = None if ns == "_all" else ns
    return {"secrets": get_k8s_secrets(ns_param)}

@app.get("/api/v1/k8s/namespaces/{ns}/events", dependencies=[Depends(require_auth)])
async def k8s_events(ns: str):
    from api_gateway.k8s_resources import get_k8s_events
    ns_param = None if ns == "_all" else ns
    return {"events": get_k8s_events(ns_param)}

@app.get("/api/v1/k8s/pvs", dependencies=[Depends(require_auth)])
async def k8s_pvs():
    from api_gateway.k8s_resources import get_k8s_pvs
    return {"pvs": get_k8s_pvs()}

@app.get("/api/v1/k8s/pvcs", dependencies=[Depends(require_auth)])
async def k8s_pvcs():
    from api_gateway.k8s_resources import get_k8s_pvcs
    return {"pvcs": get_k8s_pvcs()}

@app.get("/api/v1/k8s/storageclasses", dependencies=[Depends(require_auth)])
async def k8s_storageclasses():
    from api_gateway.k8s_resources import get_k8s_storageclasses
    return {"storageclasses": get_k8s_storageclasses()}

@app.get("/api/v1/k8s/namespaces/{ns}/ingresses", dependencies=[Depends(require_auth)])
async def k8s_ingresses(ns: str):
    from api_gateway.k8s_resources import get_k8s_ingresses
    ns_param = None if ns == "_all" else ns
    return {"ingresses": get_k8s_ingresses(ns_param)}

# ════════════════════════════════════════════════
# AI CHATBOT — Gemini-Powered Monitoring Assistant
# Admin-only: queries monitoring data + Gemini API
# ════════════════════════════════════════════════

@app.get("/api/v1/settings/gemini")
async def get_gemini_settings(user: dict = Depends(require_role(["admin"]))):
    """Get Gemini AI settings (admin only)."""
    api_key = get_setting("gemini_api_key", "")
    enabled = get_setting("gemini_enabled", False)
    model = get_setting("gemini_model", "gemini-2.0-flash")
    return {
        "api_key": ("*" * 20 + api_key[-4:]) if api_key and len(api_key) > 4 else "",
        "enabled": enabled,
        "has_key": bool(api_key),
        "model": model,
    }

@app.put("/api/v1/settings/gemini")
async def update_gemini_settings(request: Request, user: dict = Depends(require_role(["admin"]))):
    """Update Gemini AI settings (admin only)."""
    body = await request.json()
    if "api_key" in body and body["api_key"] and not body["api_key"].startswith("*"):
        set_setting("gemini_api_key", body["api_key"])
    if "enabled" in body:
        set_setting("gemini_enabled", body["enabled"])
    if "model" in body and body["model"]:
        set_setting("gemini_model", body["model"])
    insert_audit_log(user["id"], user["username"], "update_gemini_settings", "settings", {"enabled": body.get("enabled"), "model": body.get("model")})
    return {"status": "updated"}

@app.post("/api/v1/settings/gemini/test")
async def test_gemini_connection(user: dict = Depends(require_role(["admin"]))):
    """Test Gemini API connection (admin only)."""
    api_key = get_setting("gemini_api_key", "")
    if not api_key:
        raise HTTPException(400, "Gemini API key not configured")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model = get_setting("gemini_model", "gemini-2.0-flash")
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: OK"
        )
        return {"status": "connected", "model": model, "response": response.text.strip()}
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {str(e)}")

@app.get("/api/v1/settings/gemini/models")
async def list_gemini_models(user: dict = Depends(require_role(["admin"]))):
    """List available Gemini models."""
    api_key = get_setting("gemini_api_key", "")
    if not api_key:
        raise HTTPException(400, "Gemini API key not configured")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        models = []
        for m in client.models.list():
            if "generateContent" in (m.supported_actions or []):
                models.append({"id": m.name.replace("models/", ""), "name": m.display_name or m.name})
        return {"models": models}
    except Exception as e:
        raise HTTPException(400, f"Failed to list models: {str(e)}")

@app.post("/api/v1/chat")
async def ai_chat(request: Request, user: dict = Depends(require_role(["admin"]))):
    """AI Chat endpoint — uses MCP Server for monitoring data access."""
    body = await request.json()
    user_message = body.get("message", "").strip()
    history = body.get("history", [])
    if not user_message:
        raise HTTPException(400, "Message required")

    api_key = get_setting("gemini_api_key", "")
    enabled = get_setting("gemini_enabled", False)
    if not api_key or not enabled:
        raise HTTPException(400, "AI Assistant chưa được cấu hình. Vui lòng thêm Gemini API Key trong Settings → AI Assistant")

    model = get_setting("gemini_model", "gemini-2.0-flash")

    try:
        from api_gateway.mcp_server import chat as mcp_chat
        reply = await mcp_chat(api_key, model, user_message, history)
        return {"reply": reply}
    except Exception as e:
        logger.error(f"MCP Chat error: {e}")
        raise HTTPException(500, f"AI error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
