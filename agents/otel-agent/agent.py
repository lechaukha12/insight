"""
Insight OpenTelemetry Agent v5.1.0

Receives OTLP data (traces + metrics) via HTTP/JSON and forwards to Insight Core API.
Acts as an OTLP-compatible collector/receiver.

Endpoints:
- POST /v1/traces - Receive OTLP trace data
- POST /v1/metrics - Receive OTLP metric data
- GET /health - Health check

Converts OTLP format → Insight API format and forwards:
- Traces → /api/v1/traces (span summaries) + /api/v1/events (error spans)
- Metrics → /api/v1/metrics (standard metric format)
"""

import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from threading import Thread

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ─── Configuration ───

CORE_API_URL = os.getenv("INSIGHT_CORE_URL", "http://localhost:8080")
API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")
AGENT_ID = os.getenv("AGENT_ID", f"otel-agent-{socket.gethostname()}")
AGENT_NAME = os.getenv("AGENT_NAME", f"OpenTelemetry Agent ({socket.gethostname()})")
LISTEN_PORT = int(os.getenv("OTEL_PORT", "4318"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("insight.otel-agent")

# ─── FastAPI App ───

app = FastAPI(title="Insight OTLP Receiver", version="5.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Stats
stats = {"traces_received": 0, "metrics_received": 0, "spans_forwarded": 0, "errors": 0}


# ─── Core API Communication ───

def send_to_core(endpoint: str, data: dict) -> bool:
    url = f"{CORE_API_URL}{endpoint}"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        if resp.status_code < 300:
            return True
        else:
            logger.error(f"Core API error {endpoint}: {resp.status_code}")
            stats["errors"] += 1
            return False
    except Exception as e:
        logger.error(f"Core API connection failed: {e}")
        stats["errors"] += 1
        return False


# ─── OTLP Trace Processing ───

def _extract_spans(otlp_data: dict) -> list[dict]:
    """Extract span summaries from OTLP trace export request."""
    spans = []
    resource_spans = otlp_data.get("resourceSpans", [])

    for rs in resource_spans:
        # Extract service name from resource attributes
        service_name = "unknown"
        resource = rs.get("resource", {})
        for attr in resource.get("attributes", []):
            if attr.get("key") == "service.name":
                service_name = attr.get("value", {}).get("stringValue", "unknown")
                break

        scope_spans = rs.get("scopeSpans", [])
        for ss in scope_spans:
            for span in ss.get("spans", []):
                trace_id = span.get("traceId", "")
                span_id = span.get("spanId", str(uuid.uuid4())[:16])
                span_name = span.get("name", "")
                kind = span.get("kind", 0)

                # Calculate duration
                start_ns = int(span.get("startTimeUnixNano", 0))
                end_ns = int(span.get("endTimeUnixNano", 0))
                duration_ms = (end_ns - start_ns) / 1_000_000 if end_ns > start_ns else 0

                # Check status
                status = span.get("status", {})
                status_code = status.get("code", 0)  # 0=UNSET, 1=OK, 2=ERROR
                status_str = "error" if status_code == 2 else "ok"

                # Extract key attributes
                attrs = {}
                for attr in span.get("attributes", []):
                    key = attr.get("key", "")
                    val = attr.get("value", {})
                    # Extract first available value type
                    attrs[key] = val.get("stringValue") or val.get("intValue") or val.get("doubleValue") or val.get("boolValue", "")

                spans.append({
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "span_name": span_name,
                    "service_name": service_name,
                    "duration_ms": round(duration_ms, 2),
                    "status": status_str,
                    "attributes": attrs,
                    "kind": kind,
                    "timestamp": datetime.fromtimestamp(start_ns / 1_000_000_000, tz=timezone.utc).isoformat() if start_ns else None,
                })

    return spans


# ─── OTLP Metric Processing ───

def _extract_metrics(otlp_data: dict) -> list[dict]:
    """Extract metrics from OTLP metric export request."""
    metrics = []
    resource_metrics = otlp_data.get("resourceMetrics", [])

    for rm in resource_metrics:
        # Extract host/service labels
        labels = {}
        resource = rm.get("resource", {})
        for attr in resource.get("attributes", []):
            key = attr.get("key", "")
            val = attr.get("value", {})
            value = val.get("stringValue") or val.get("intValue") or val.get("doubleValue", "")
            if key in ("host.name", "service.name", "service.namespace"):
                labels[key.replace(".", "_")] = value

        scope_metrics = rm.get("scopeMetrics", [])
        for sm in scope_metrics:
            for metric in sm.get("metrics", []):
                name = metric.get("name", "")
                unit = metric.get("unit", "")

                # Handle different metric data types
                data_points = []
                if "gauge" in metric:
                    data_points = metric["gauge"].get("dataPoints", [])
                elif "sum" in metric:
                    data_points = metric["sum"].get("dataPoints", [])
                elif "histogram" in metric:
                    # Use sum/count for histogram
                    for dp in metric["histogram"].get("dataPoints", []):
                        count = dp.get("count", 0)
                        total = dp.get("sum", 0)
                        avg = total / count if count > 0 else 0
                        metrics.append({
                            "metric_name": name,
                            "metric_value": avg,
                            "labels": {**labels, "unit": unit, "type": "histogram_avg"},
                        })
                    continue

                for dp in data_points:
                    value = dp.get("asDouble") or dp.get("asInt") or 0
                    metrics.append({
                        "metric_name": name,
                        "metric_value": float(value),
                        "labels": {**labels, "unit": unit},
                    })

    return metrics


# ─── HTTP Endpoints ───

@app.get("/health")
async def health():
    return {"status": "ok", "agent": AGENT_ID, "version": "5.1.0", "stats": stats}


@app.post("/v1/traces")
async def receive_traces(request: Request):
    """OTLP HTTP Trace Receiver."""
    try:
        data = await request.json()
    except Exception:
        body = await request.body()
        try:
            data = json.loads(body)
        except Exception:
            return {"partialSuccess": {"rejectedSpans": 0, "errorMessage": "invalid JSON"}}

    spans = _extract_spans(data)
    stats["traces_received"] += 1
    stats["spans_forwarded"] += len(spans)
    logger.info(f"Received {len(spans)} spans")

    if spans:
        # Forward trace summaries to Core API
        send_to_core("/api/v1/traces", {
            "agent_id": AGENT_ID,
            "traces": spans,
        })

        # Send error spans as events
        error_spans = [s for s in spans if s["status"] == "error"]
        if error_spans:
            events = [{
                "level": "error",
                "title": f"Trace Error: {s['span_name']}",
                "message": f"Service {s['service_name']}: {s['span_name']} failed ({s['duration_ms']:.0f}ms)",
                "source": f"otel/{s['service_name']}",
                "details": s.get("attributes", {}),
            } for s in error_spans[:20]]

            send_to_core("/api/v1/events", {
                "agent_id": AGENT_ID,
                "agent_name": AGENT_NAME,
                "agent_type": "opentelemetry",
                "hostname": socket.gethostname(),
                "events": events,
            })

    return {"partialSuccess": {}}


@app.post("/v1/metrics")
async def receive_metrics(request: Request):
    """OTLP HTTP Metric Receiver."""
    try:
        data = await request.json()
    except Exception:
        body = await request.body()
        try:
            data = json.loads(body)
        except Exception:
            return {"partialSuccess": {"rejectedDataPoints": 0, "errorMessage": "invalid JSON"}}

    metrics = _extract_metrics(data)
    stats["metrics_received"] += 1
    logger.info(f"Received {len(metrics)} metrics")

    if metrics:
        send_to_core("/api/v1/metrics", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "opentelemetry",
            "hostname": socket.gethostname(),
            "metrics": metrics,
        })

    return {"partialSuccess": {}}


@app.post("/v1/logs")
async def receive_logs(request: Request):
    """OTLP HTTP Log Receiver (basic support)."""
    try:
        data = await request.json()
    except Exception:
        return {"partialSuccess": {}}

    logs = []
    for rl in data.get("resourceLogs", []):
        for sl in rl.get("scopeLogs", []):
            for lr in sl.get("logRecords", []):
                severity = lr.get("severityText", "INFO").upper()
                level = "critical" if severity in ("FATAL", "CRITICAL") else \
                        "error" if severity == "ERROR" else \
                        "warning" if ("WARN" in severity) else "info"
                body = lr.get("body", {}).get("stringValue", "")
                logs.append({
                    "level": level,
                    "source": "otel",
                    "message": body[:500],
                })

    if logs:
        send_to_core("/api/v1/logs", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "opentelemetry",
            "hostname": socket.gethostname(),
            "logs": logs,
        })

    return {"partialSuccess": {}}


# ─── Heartbeat Background Thread ───

def _heartbeat_loop():
    """Send periodic heartbeat to Core API."""
    while True:
        try:
            send_to_core(f"/api/v1/agents/{AGENT_ID}/heartbeat", {})
            # Also register agent
            send_to_core("/api/v1/metrics", {
                "agent_id": AGENT_ID,
                "agent_name": AGENT_NAME,
                "agent_type": "opentelemetry",
                "hostname": socket.gethostname(),
                "metrics": [{
                    "metric_name": "otel_spans_received",
                    "metric_value": float(stats["spans_forwarded"]),
                    "labels": {"host": socket.gethostname()},
                }],
            })
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
        time.sleep(HEARTBEAT_INTERVAL)


# ─── Startup ───

@app.on_event("startup")
async def startup():
    logger.info(f"Insight OpenTelemetry Agent v5.1.0 starting...")
    logger.info(f"   Agent ID: {AGENT_ID}")
    logger.info(f"   Core URL: {CORE_API_URL}")
    logger.info(f"   OTLP HTTP Port: {LISTEN_PORT}")

    # Start heartbeat thread
    t = Thread(target=_heartbeat_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
