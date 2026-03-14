"""
Insight Data Collector — High-throughput data ingestion service.
Handles: agent registration, metrics, events, logs, processes, traces, OTLP receivers.
Port: 8081 | Auth: API key + Agent token (no JWT needed).
"""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.db import (
    init_db, register_agent, get_or_create_agent, get_agent,
    update_agent_heartbeat, insert_metrics, insert_events,
    insert_logs, insert_traces, save_process_snapshot,
    verify_agent_token, connect_agent,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("insight.collector")

# ─── Auth ───
API_KEY = os.getenv("INSIGHT_API_KEY", "")
if not API_KEY:
    import secrets as _sec
    API_KEY = _sec.token_urlsafe(32)
    logger.warning(f"INSIGHT_API_KEY not set, generated random key")


async def require_api_key(request: Request):
    """Accept either INSIGHT_API_KEY via X-API-Key header, or a valid agent token via X-Agent-Token."""
    # Check X-Agent-Token first (agents use this)
    agent_token = request.headers.get("X-Agent-Token", "")
    if agent_token:
        token_record = verify_agent_token(agent_token)
        if token_record:
            return
        raise HTTPException(status_code=401, detail="Invalid or revoked agent token")
    # Fallback to API key
    key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if key and key == API_KEY:
        return
    raise HTTPException(status_code=401, detail="Invalid API Key or Agent Token")


async def require_agent_token(request: Request):
    agent_token = request.headers.get("X-Agent-Token", "")
    if not agent_token:
        raise HTTPException(status_code=401, detail="X-Agent-Token header required")
    token_record = verify_agent_token(agent_token)
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent token")
    request.state.token_record = token_record


# ─── App ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Insight Data Collector v1.0.0 starting...")
    init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down")

app = FastAPI(title="Insight Data Collector", version="1.0.0", lifespan=lifespan)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "data-collector", "version": "1.0.0"}


# ════════════════════════════════════════════════
# AGENT REGISTRATION
# ════════════════════════════════════════════════

@app.post("/api/v1/agents/register", dependencies=[Depends(require_agent_token)])
async def register_new_agent(request: Request):
    body = await request.json()
    agent = register_agent(
        name=body.get("name", "unnamed"),
        agent_type=body.get("agent_type", "unknown"),
        hostname=body.get("hostname", ""),
        labels=body.get("labels", {}),
        cluster_id=body.get("cluster_id", "default"),
        agent_category=body.get("agent_category"),
    )
    return {"status": "registered", "agent": agent}


@app.post("/api/v1/agents/connect")
async def agent_connect(request: Request):
    """Token-based agent auto-registration."""
    agent_token = request.headers.get("X-Agent-Token", "")
    if not agent_token:
        raise HTTPException(status_code=401, detail="X-Agent-Token header required")
    token_record = verify_agent_token(agent_token)
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent token")
    body = await request.json()
    requested_type = body.get("agent_type", "system")
    if token_record.get("agent_type") not in ("any", requested_type):
        raise HTTPException(status_code=403, detail=f"Token restricted to type '{token_record['agent_type']}', got '{requested_type}'")
    client_ip = request.client.host if request.client else ""
    body["ip_address"] = client_ip
    result = connect_agent(token_record, body)
    return {
        "status": "connected",
        "agent_id": result["id"],
        "agent_name": result["name"],
        "agent_category": result["agent_category"],
        "server_time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


@app.post("/api/v1/agents/{agent_id}/heartbeat", dependencies=[Depends(require_agent_token)])
async def agent_heartbeat(agent_id: str):
    update_agent_heartbeat(agent_id)
    return {"status": "ok"}


# ════════════════════════════════════════════════
# METRICS INGESTION
# ════════════════════════════════════════════════

@app.post("/api/v1/metrics", dependencies=[Depends(require_api_key)])
async def receive_metrics(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id", "")
    get_or_create_agent(agent_id, body.get("agent_name", agent_id), body.get("agent_type", "unknown"),
                        body.get("hostname", ""), body.get("cluster_id", "default"),
                        agent_category=body.get("agent_category"))
    metrics = body.get("metrics", [])
    if metrics:
        insert_metrics(agent_id, metrics)
        logger.info(f"Received {len(metrics)} metrics from {agent_id}")
    return {"status": "ok", "received": len(metrics)}


# ════════════════════════════════════════════════
# EVENTS INGESTION
# ════════════════════════════════════════════════

@app.post("/api/v1/events", dependencies=[Depends(require_api_key)])
async def receive_events(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id", "")
    get_or_create_agent(agent_id, body.get("agent_name", agent_id), body.get("agent_type", "unknown"),
                        agent_category=body.get("agent_category"))
    events = body.get("events", [])
    if events:
        insert_events(agent_id, events)
        logger.info(f"Received {len(events)} events from {agent_id}")
    return {"status": "ok", "received": len(events)}


# ════════════════════════════════════════════════
# LOGS INGESTION
# ════════════════════════════════════════════════

@app.post("/api/v1/logs", dependencies=[Depends(require_api_key)])
async def receive_logs(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id", "")
    get_or_create_agent(agent_id, body.get("agent_name", agent_id), body.get("agent_type", "unknown"),
                        agent_category=body.get("agent_category"))
    logs = body.get("logs", [])
    if logs:
        insert_logs(agent_id, logs)
        logger.info(f"Received {len(logs)} logs from {agent_id}")
    return {"status": "ok", "received": len(logs)}


# ════════════════════════════════════════════════
# PROCESSES INGESTION
# ════════════════════════════════════════════════

@app.post("/api/v1/processes", dependencies=[Depends(require_api_key)])
async def receive_processes(request: Request):
    data = await request.json()
    agent_id = data.get("agent_id")
    processes = data.get("processes", [])
    if not agent_id:
        raise HTTPException(400, "agent_id required")
    save_process_snapshot(agent_id, processes)
    return {"status": "ok", "received": len(processes)}


# ════════════════════════════════════════════════
# TRACES INGESTION
# ════════════════════════════════════════════════

@app.post("/api/v1/traces", dependencies=[Depends(require_api_key)])
async def receive_traces(request: Request):
    data = await request.json()
    agent_id = data.get("agent_id")
    traces = data.get("traces", [])
    if not agent_id:
        raise HTTPException(400, "agent_id required")
    insert_traces(agent_id, traces)
    return {"status": "ok", "received": len(traces)}


# ════════════════════════════════════════════════
# OTLP HTTP RECEIVERS (OpenTelemetry Standard)
# ════════════════════════════════════════════════

def _pb_attr_value(kv):
    v = kv.value
    if v.HasField("string_value"): return v.string_value
    if v.HasField("int_value"): return v.int_value
    if v.HasField("double_value"): return v.double_value
    if v.HasField("bool_value"): return v.bool_value
    return ""

def _pb_get_service_name(resource) -> str:
    for kv in resource.attributes:
        if kv.key == "service.name":
            return _pb_attr_value(kv) or "unknown-service"
    return "unknown-service"

def _otlp_ensure_agent(service_name: str):
    agent_id = f"otel-{service_name}"
    get_or_create_agent(agent_id, service_name, "opentelemetry", "", "default", agent_category="application")
    return agent_id


@app.post("/v1/traces")
async def otlp_receive_traces(request: Request):
    """OTLP HTTP trace receiver — protobuf and JSON."""
    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    if not raw:
        return JSONResponse(status_code=200, content={})
    all_traces = []
    try:
        if "protobuf" in content_type or "proto" in content_type:
            from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
            req = ExportTraceServiceRequest()
            req.ParseFromString(raw)
            for rs in req.resource_spans:
                service_name = _pb_get_service_name(rs.resource)
                agent_id = _otlp_ensure_agent(service_name)
                for ss in rs.scope_spans:
                    for span in ss.spans:
                        duration_ms = (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000
                        status = "error" if span.status.code == 2 else "ok"
                        attrs = {kv.key: str(_pb_attr_value(kv)) for kv in span.attributes}
                        all_traces.append({
                            "trace_id": span.trace_id.hex(), "span_id": span.span_id.hex(),
                            "span_name": span.name, "service_name": service_name,
                            "duration_ms": round(duration_ms, 2), "status": status,
                            "attributes": attrs, "agent_id": agent_id,
                        })
        else:
            body = json.loads(raw)
            for rs in body.get("resourceSpans", []):
                resource = rs.get("resource", {})
                svc_attrs = resource.get("attributes", [])
                service_name = next((a.get("value",{}).get("stringValue","") for a in svc_attrs if a.get("key") == "service.name"), "unknown-service")
                agent_id = _otlp_ensure_agent(service_name)
                for ss in rs.get("scopeSpans", []):
                    for span in ss.get("spans", []):
                        start_ns, end_ns = int(span.get("startTimeUnixNano", 0)), int(span.get("endTimeUnixNano", 0))
                        duration_ms = (end_ns - start_ns) / 1_000_000 if start_ns and end_ns else 0
                        status = "error" if span.get("status", {}).get("code", 0) == 2 else "ok"
                        attrs = {a["key"]: str(a.get("value",{}).get("stringValue","") or a.get("value",{}).get("intValue","")) for a in span.get("attributes",[])}
                        all_traces.append({
                            "trace_id": span.get("traceId", ""), "span_id": span.get("spanId", ""),
                            "span_name": span.get("name", ""), "service_name": service_name,
                            "duration_ms": round(duration_ms, 2), "status": status,
                            "attributes": attrs, "agent_id": agent_id,
                        })
    except Exception as e:
        logger.error(f"OTLP traces parse error: {e}")
        return JSONResponse(status_code=200, content={})

    if all_traces:
        by_agent: dict[str, list] = {}
        for t in all_traces:
            aid = t.pop("agent_id")
            by_agent.setdefault(aid, []).append(t)
        for aid, traces in by_agent.items():
            insert_traces(aid, traces)
        logger.info(f"OTLP: Received {len(all_traces)} spans from {len(by_agent)} services")
    return JSONResponse(status_code=200, content={})


@app.post("/v1/metrics")
async def otlp_receive_metrics(request: Request):
    """OTLP HTTP metrics receiver — protobuf and JSON."""
    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    if not raw:
        return JSONResponse(status_code=200, content={})
    all_metrics: dict[str, list] = {}
    try:
        if "protobuf" in content_type or "proto" in content_type:
            from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
            req = ExportMetricsServiceRequest()
            req.ParseFromString(raw)
            for rm in req.resource_metrics:
                service_name = _pb_get_service_name(rm.resource)
                agent_id = _otlp_ensure_agent(service_name)
                for sm in rm.scope_metrics:
                    for metric in sm.metrics:
                        data_points = list(metric.gauge.data_points) or list(metric.sum.data_points)
                        for dp in data_points:
                            value = dp.as_double or dp.as_int
                            labels = {kv.key: str(_pb_attr_value(kv)) for kv in dp.attributes}
                            labels["service_name"] = service_name
                            all_metrics.setdefault(agent_id, []).append({
                                "metric_name": metric.name, "metric_value": float(value), "labels": labels,
                            })
        else:
            body = json.loads(raw)
            for rm in body.get("resourceMetrics", []):
                svc_attrs = rm.get("resource", {}).get("attributes", [])
                service_name = next((a.get("value",{}).get("stringValue","") for a in svc_attrs if a.get("key") == "service.name"), "unknown-service")
                agent_id = _otlp_ensure_agent(service_name)
                for sm in rm.get("scopeMetrics", []):
                    for metric in sm.get("metrics", []):
                        for key in ("gauge", "sum"):
                            for dp in metric.get(key, {}).get("dataPoints", []):
                                value = dp.get("asDouble") or dp.get("asInt", 0)
                                labels = {a["key"]: str(a.get("value",{}).get("stringValue","")) for a in dp.get("attributes",[])}
                                labels["service_name"] = service_name
                                all_metrics.setdefault(agent_id, []).append({
                                    "metric_name": metric.get("name",""), "metric_value": float(value) if value else 0.0, "labels": labels,
                                })
    except Exception as e:
        logger.error(f"OTLP metrics parse error: {e}")
        return JSONResponse(status_code=200, content={})

    for agent_id, metrics in all_metrics.items():
        insert_metrics(agent_id, metrics)
        logger.info(f"OTLP: Received {len(metrics)} metrics from {agent_id}")
    return JSONResponse(status_code=200, content={})


@app.post("/v1/logs")
async def otlp_receive_logs(request: Request):
    """OTLP HTTP logs receiver — protobuf and JSON."""
    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    if not raw:
        return JSONResponse(status_code=200, content={})
    all_logs: dict[str, list] = {}
    try:
        if "protobuf" in content_type or "proto" in content_type:
            from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
            req = ExportLogsServiceRequest()
            req.ParseFromString(raw)
            for rl in req.resource_logs:
                service_name = _pb_get_service_name(rl.resource)
                agent_id = _otlp_ensure_agent(service_name)
                for sl in rl.scope_logs:
                    for lr in sl.log_records:
                        severity = lr.severity_text.lower() if lr.severity_text else "info"
                        message = lr.body.string_value if lr.body.HasField("string_value") else str(lr.body)
                        all_logs.setdefault(agent_id, []).append({
                            "log_level": severity if severity in ("debug","info","warning","error","critical") else "info",
                            "message": message, "source": service_name, "namespace": "", "pod_name": "",
                        })
        else:
            body = json.loads(raw)
            for rl in body.get("resourceLogs", []):
                svc_attrs = rl.get("resource", {}).get("attributes", [])
                service_name = next((a.get("value",{}).get("stringValue","") for a in svc_attrs if a.get("key") == "service.name"), "unknown-service")
                agent_id = _otlp_ensure_agent(service_name)
                for sl in rl.get("scopeLogs", []):
                    for lr in sl.get("logRecords", []):
                        severity = lr.get("severityText", "info").lower()
                        body_val = lr.get("body", {})
                        message = body_val.get("stringValue", "") if isinstance(body_val, dict) else str(body_val)
                        all_logs.setdefault(agent_id, []).append({
                            "log_level": severity if severity in ("debug","info","warning","error","critical") else "info",
                            "message": message, "source": service_name, "namespace": "", "pod_name": "",
                        })
    except Exception as e:
        logger.error(f"OTLP logs parse error: {e}")
        return JSONResponse(status_code=200, content={})

    for agent_id, logs in all_logs.items():
        insert_logs(agent_id, logs)
        logger.info(f"OTLP: Received {len(logs)} logs from {agent_id}")
    return JSONResponse(status_code=200, content={})
