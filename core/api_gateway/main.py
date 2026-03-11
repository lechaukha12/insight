"""
Insight Monitoring System - API Gateway v5.0.0
RBAC, Webhooks, WebSocket, Multi-cluster support.
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.db import (
    init_db, register_agent, get_or_create_agent, list_agents, get_agent,
    update_agent_heartbeat, insert_metrics, get_metrics, get_latest_metrics_per_agent,
    get_metrics_timeseries, get_event_counts_by_hour,
    insert_events, get_events, get_event_counts, acknowledge_event,
    insert_logs, get_logs,
    save_alert_config, get_alert_configs, delete_alert_config,
    save_report, get_reports, get_setting, set_setting,
    create_user, get_user_by_username, get_user_by_id, list_users, update_user_password, delete_user,
    create_cluster, list_clusters, get_cluster,
    save_rule, get_rules, delete_rule, toggle_rule,
    insert_audit_log, get_audit_logs,
    save_webhook, get_webhooks, delete_webhook, toggle_webhook,
    save_process_snapshot, get_process_snapshot,
    insert_traces, get_traces,
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
    logger.info("Insight API Gateway v5.0.0 starting...")
    init_db()
    ensure_default_admin()
    logger.info("Database and auth initialized")
    yield
    logger.info("Shutting down")

app = FastAPI(title="Insight Monitoring System", version="5.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")

# ─── Health ───
@app.get("/health")
async def health():
    return {"status": "ok", "version": "5.0.0", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/")
async def root():
    return {"name": "Insight Monitoring System", "version": "5.0.0"}

# ════════════════════════════════════════════════
# AUTH ROUTES
# ════════════════════════════════════════════════

@app.post("/api/v1/auth/login")
async def login(request: Request):
    body = await request.json()
    username, password = body.get("username", ""), body.get("password", "")
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
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
    return {"users": list_users(), "total": len(list_users())}

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
# AGENT ROUTES
# ════════════════════════════════════════════════

@app.post("/api/v1/agents/register")
async def register_new_agent(request: Request):
    body = await request.json()
    agent = register_agent(name=body.get("name","unnamed"), agent_type=body.get("agent_type","unknown"),
                           hostname=body.get("hostname",""), labels=body.get("labels",{}), cluster_id=body.get("cluster_id","default"))
    return {"status": "registered", "agent": agent}

@app.get("/api/v1/agents")
async def get_all_agents(cluster_id: str = Query(None)):
    agents = list_agents(cluster_id=cluster_id)
    return {"agents": agents, "total": len(agents)}

@app.get("/api/v1/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    agent = get_agent(agent_id)
    if not agent: raise HTTPException(404, "Agent not found")
    return agent

@app.post("/api/v1/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str):
    update_agent_heartbeat(agent_id)
    return {"status": "ok"}

# ════════════════════════════════════════════════
# METRICS ROUTES
# ════════════════════════════════════════════════

@app.post("/api/v1/metrics")
async def receive_metrics(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id","")
    get_or_create_agent(agent_id, body.get("agent_name",agent_id), body.get("agent_type","unknown"),
                        body.get("hostname",""), body.get("cluster_id","default"))
    metrics = body.get("metrics", [])
    if metrics:
        insert_metrics(agent_id, metrics)
        logger.info(f"Received {len(metrics)} metrics from {agent_id}")
        await check_metric_alerts(agent_id, metrics)
        await ws_manager.broadcast({"type": "metrics", "agent_id": agent_id, "count": len(metrics)})
    return {"status": "ok", "received": len(metrics)}

@app.get("/api/v1/metrics")
async def query_metrics(agent_id: str = Query(None), metric_name: str = Query(None),
                        last_hours: int = Query(24), limit: int = Query(1000)):
    data = get_metrics(agent_id=agent_id, metric_name=metric_name, last_hours=last_hours, limit=limit)
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
# EVENTS ROUTES
# ════════════════════════════════════════════════

@app.post("/api/v1/events")
async def receive_events(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id","")
    get_or_create_agent(agent_id, body.get("agent_name",agent_id), body.get("agent_type","unknown"))
    events = body.get("events", [])
    if events:
        insert_events(agent_id, events)
        logger.info(f"Received {len(events)} events from {agent_id}")
        for e in events:
            if e.get("level","info") in ("error","critical"):
                await trigger_alert(e)
        await ws_manager.broadcast({"type":"events","agent_id":agent_id,"count":len(events),
            "events":[{"title":e.get("title",""),"level":e.get("level","info")} for e in events[:5]]})
    return {"status": "ok", "received": len(events)}

@app.get("/api/v1/events")
async def query_events(agent_id: str = Query(None), level: str = Query(None),
                       last_hours: int = Query(24), limit: int = Query(200)):
    data = get_events(agent_id=agent_id, level=level, last_hours=last_hours, limit=limit)
    return {"events": data, "total": len(data)}

@app.post("/api/v1/events/{event_id}/acknowledge")
async def ack_event(event_id: str):
    acknowledge_event(event_id)
    return {"status": "acknowledged"}

# ════════════════════════════════════════════════
# LOGS ROUTES
# ════════════════════════════════════════════════

@app.post("/api/v1/logs")
async def receive_logs(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id","")
    get_or_create_agent(agent_id, body.get("agent_name",agent_id), body.get("agent_type","unknown"))
    logs = body.get("logs", [])
    if logs:
        insert_logs(agent_id, logs)
        error_logs = [l for l in logs if l.get("log_level") == "error"]
        if error_logs: await trigger_log_alert(agent_id, error_logs)
    return {"status": "ok", "received": len(logs)}

@app.get("/api/v1/logs")
async def query_logs(agent_id: str = Query(None), last_hours: int = Query(24), limit: int = Query(500)):
    return {"logs": get_logs(agent_id=agent_id, last_hours=last_hours, limit=limit)}

# ════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════

@app.get("/api/v1/dashboard/summary")
async def dashboard_summary(cluster_id: str = Query(None)):
    agents = list_agents(cluster_id=cluster_id)
    event_counts = get_event_counts(last_hours=24)
    latest_metrics = get_latest_metrics_per_agent()
    recent_events = get_events(last_hours=24, limit=50)
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

@app.get("/api/v1/settings/alerts")
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

@app.get("/api/v1/webhooks")
async def list_all_webhooks():
    return {"webhooks": get_webhooks(), "total": len(get_webhooks())}

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

@app.get("/api/v1/rules")
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
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping": await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# ════════════════════════════════════════════════
# INTERNAL ALERT LOGIC
# ════════════════════════════════════════════════

async def trigger_alert(event: dict):
    try:
        from alert_service.providers import alert_manager
        configs = get_alert_configs()
        await alert_manager.send_alert(level=event.get("level","error"), title=event.get("title",""),
                                       message=event.get("message",""), source=event.get("source",""), configs=configs)
    except Exception as e: logger.error(f"Alert trigger failed: {e}")
    # Send to webhooks
    try:
        from api_gateway.webhook_sender import send_to_all_webhooks
        webhooks = get_webhooks(enabled_only=True)
        await send_to_all_webhooks(webhooks, event.get("level","error"), event.get("title",""),
                                   event.get("message",""), event.get("source",""))
    except Exception as e: logger.error(f"Webhook alert failed: {e}")

async def trigger_log_alert(agent_id: str, error_logs: list[dict]):
    try:
        from alert_service.providers import alert_manager
        configs = get_alert_configs()
        summary = f"Detected {len(error_logs)} error logs"
        details = "\n".join(f"[{l.get('namespace','')}] {l.get('pod_name','')}: {l.get('message','')[:100]}" for l in error_logs[:5])
        await alert_manager.send_alert(level="error", title=summary, message=details, source=f"agent:{agent_id}", configs=configs)
    except Exception as e: logger.error(f"Log alert failed: {e}")

async def check_metric_alerts(agent_id: str, metrics: list[dict]):
    rules = get_rules(enabled_only=True)
    for m in metrics:
        name, value = m.get("metric_name",""), m.get("metric_value",0)
        for rule in rules:
            if rule["metric_name"] != name: continue
            op, threshold = rule["operator"], rule["threshold"]
            triggered = (op == ">" and value > threshold) or (op == ">=" and value >= threshold) or \
                        (op == "<" and value < threshold) or (op == "<=" and value <= threshold) or \
                        (op == "==" and value == threshold)
            if triggered:
                try:
                    from alert_service.providers import alert_manager
                    configs = get_alert_configs()
                    await alert_manager.send_alert(level="warning", title=f"Rule: {rule['name']}",
                        message=f"Agent {agent_id}: {name} = {value:.1f} ({op} {threshold})", source=f"rule:{rule['id']}", configs=configs)
                except: pass
                try:
                    from api_gateway.webhook_sender import send_to_all_webhooks
                    webhooks = get_webhooks(enabled_only=True)
                    await send_to_all_webhooks(webhooks, "warning", f"Rule: {rule['name']}",
                        f"Agent {agent_id}: {name} = {value:.1f} ({op} {threshold})", f"rule:{rule['id']}")
                except: pass

# ─── Process Monitoring ───

@app.post("/api/v1/processes", dependencies=[Depends(require_auth)])
async def receive_processes(request: Request):
    data = await request.json()
    agent_id = data.get("agent_id")
    processes = data.get("processes", [])
    if not agent_id:
        raise HTTPException(400, "agent_id required")
    save_process_snapshot(agent_id, processes)
    return {"status": "ok", "received": len(processes)}

@app.get("/api/v1/processes", dependencies=[Depends(require_auth)])
async def query_processes(agent_id: str = None):
    if not agent_id:
        raise HTTPException(400, "agent_id required")
    result = get_process_snapshot(agent_id)
    return result

# ─── Traces ───

@app.post("/api/v1/traces", dependencies=[Depends(require_auth)])
async def receive_traces(request: Request):
    data = await request.json()
    agent_id = data.get("agent_id")
    traces = data.get("traces", [])
    if not agent_id:
        raise HTTPException(400, "agent_id required")
    insert_traces(agent_id, traces)
    return {"status": "ok", "received": len(traces)}

@app.get("/api/v1/traces", dependencies=[Depends(require_auth)])
async def query_traces(agent_id: str = None, last_hours: int = 24, limit: int = 100):
    result = get_traces(agent_id=agent_id, last_hours=last_hours, limit=limit)
    return {"traces": result, "total": len(result)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

