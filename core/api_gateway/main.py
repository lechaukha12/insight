"""
Insight Monitoring System - API Gateway
Main FastAPI application serving as the entry point for all agents and dashboard.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.db import (
    init_db,
    register_agent,
    get_or_create_agent,
    list_agents,
    get_agent,
    update_agent_heartbeat,
    insert_metrics,
    get_metrics,
    get_latest_metrics_per_agent,
    get_metrics_timeseries,
    get_event_counts_by_hour,
    insert_events,
    get_events,
    get_event_counts,
    acknowledge_event,
    insert_logs,
    get_logs,
    save_alert_config,
    get_alert_configs,
    delete_alert_config,
    save_report,
    get_reports,
    get_setting,
    set_setting,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("insight.gateway")


# ─── Lifespan ───


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Insight API Gateway starting...")
    init_db()
    logger.info("✅ Database initialized")
    yield
    logger.info("👋 Insight API Gateway shutting down")


# ─── App ───


app = FastAPI(
    title="Insight Monitoring System",
    description="Central monitoring platform for multi-agent infrastructure monitoring",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to dashboard URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key for agent auth (simple for MVP)
API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")


def verify_api_key(x_api_key: str = Header(None)):
    """Simple API key auth for agents."""
    if x_api_key and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ─── Health ───


@app.get("/health")
async def health():
    return {"status": "ok", "service": "insight-api-gateway", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/")
async def root():
    return {
        "name": "Insight Monitoring System",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "agents": "/api/v1/agents",
            "metrics": "/api/v1/metrics",
            "events": "/api/v1/events",
            "logs": "/api/v1/logs",
            "reports": "/api/v1/reports",
            "settings": "/api/v1/settings",
            "dashboard": "/api/v1/dashboard/summary",
        },
    }


# ─── Agent Routes ───


@app.post("/api/v1/agents/register")
async def register_new_agent(request: Request):
    body = await request.json()
    agent = register_agent(
        name=body.get("name", "unnamed"),
        agent_type=body.get("agent_type", "unknown"),
        hostname=body.get("hostname", ""),
        labels=body.get("labels", {}),
    )
    logger.info(f"Agent registered: {agent['name']} ({agent['agent_type']})")
    return {"status": "registered", "agent": agent}


@app.get("/api/v1/agents")
async def get_all_agents():
    agents = list_agents()
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
    
    # Auto-register/update agent
    get_or_create_agent(agent_id, body.get("agent_name", agent_id), agent_type, hostname)

    metrics = body.get("metrics", [])
    if metrics:
        insert_metrics(agent_id, metrics)
        logger.info(f"Received {len(metrics)} metrics from agent {agent_id}")

    # Check if any metrics trigger alerts (e.g., high CPU)
    await check_metric_alerts(agent_id, metrics)

    return {"status": "ok", "received": len(metrics)}


@app.get("/api/v1/metrics")
async def query_metrics(
    agent_id: str = Query(None),
    metric_name: str = Query(None),
    last_hours: int = Query(24),
    limit: int = Query(1000),
):
    data = get_metrics(agent_id=agent_id, metric_name=metric_name, last_hours=last_hours, limit=limit)
    return {"metrics": data, "total": len(data)}


# ─── Chart Data Routes ───


@app.get("/api/v1/charts/metrics")
async def chart_metrics(
    agent_id: str = Query(None),
    last_hours: int = Query(6),
    metric_names: str = Query(None),
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

        # Trigger alerts for error/critical events
        for event in events:
            level = event.get("level", "info")
            if level in ("error", "critical"):
                await trigger_alert(event)

    return {"status": "ok", "received": len(events)}


@app.get("/api/v1/events")
async def query_events(
    agent_id: str = Query(None),
    level: str = Query(None),
    last_hours: int = Query(24),
    limit: int = Query(200),
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
    agent_type = body.get("agent_type", "unknown")

    get_or_create_agent(agent_id, body.get("agent_name", agent_id), agent_type)

    logs = body.get("logs", [])
    if logs:
        insert_logs(agent_id, logs)
        logger.info(f"Received {len(logs)} log entries from agent {agent_id}")

        # Trigger alerts for error logs
        error_logs = [l for l in logs if l.get("log_level") == "error"]
        if error_logs:
            await trigger_log_alert(agent_id, error_logs)

    return {"status": "ok", "received": len(logs)}


@app.get("/api/v1/logs")
async def query_logs(
    agent_id: str = Query(None),
    last_hours: int = Query(24),
    limit: int = Query(500),
):
    data = get_logs(agent_id=agent_id, last_hours=last_hours, limit=limit)
    return {"logs": data, "total": len(data)}


# ─── Dashboard Routes ───


@app.get("/api/v1/dashboard/summary")
async def dashboard_summary():
    agents = list_agents()
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
    configs = get_alert_configs()
    return {"configs": configs}


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


# ─── Report Routes ───


@app.post("/api/v1/reports/generate")
async def generate_and_send_report(request: Request):
    body = await request.json()
    channels = body.get("channels", ["telegram"])
    
    from report_service.reports import generate_report, format_report_telegram, format_report_email

    # Gather data
    agents = list_agents()
    metrics_by_agent = get_latest_metrics_per_agent()
    events = get_events(last_hours=24)
    logs = get_logs(last_hours=24)

    report = generate_report(agents, metrics_by_agent, events, logs, "on_demand")
    
    # Send to channels
    sent_to = []
    configs = get_alert_configs()
    
    for channel in channels:
        channel_configs = [c for c in configs if c["channel"] == channel and c.get("enabled")]
        if not channel_configs:
            continue

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
    data = get_reports(limit=limit)
    return {"reports": data, "total": len(data)}


# ─── System Settings Routes ───


@app.get("/api/v1/settings")
async def get_system_settings():
    auto_report = get_setting("auto_report", {
        "enabled": False,
        "schedule": "45 0 * * *",
        "channels": ["telegram"],
        "timezone": "Asia/Ho_Chi_Minh",
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


# ─── Internal Alert Logic ───


async def trigger_alert(event: dict):
    """Trigger alert for error/critical events."""
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
    """Trigger alert when error logs are detected."""
    try:
        from alert_service.providers import alert_manager
        configs = get_alert_configs()
        
        summary = f"Phát hiện {len(error_logs)} log lỗi"
        details = "\n".join(
            f"[{l.get('namespace', '')}] {l.get('pod_name', '')}: {l.get('message', '')[:100]}"
            for l in error_logs[:5]
        )
        
        await alert_manager.send_alert(
            level="error",
            title=summary,
            message=details,
            source=f"agent:{agent_id}",
            configs=configs,
        )
    except Exception as e:
        logger.error(f"Log alert trigger failed: {e}")


async def check_metric_alerts(agent_id: str, metrics: list[dict]):
    """Check if any metric values exceed thresholds."""
    thresholds = get_setting("metric_thresholds", {
        "cpu_percent": 90,
        "memory_percent": 90,
        "disk_percent": 95,
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
                    title=f"{name} cao bất thường: {value:.1f}%",
                    message=f"Agent {agent_id}: {name} = {value:.1f}% (ngưỡng: {thresholds[name]}%)",
                    source=f"agent:{agent_id}",
                    configs=configs,
                )
            except Exception as e:
                logger.error(f"Metric alert failed: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
