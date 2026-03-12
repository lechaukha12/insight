"""
Insight Collector v5.0.2

Receives OTLP data (traces + metrics + logs) via HTTP (protobuf or JSON)
and forwards to Insight Core API.
Acts as an OTLP-compatible collector/receiver.

Endpoints:
- POST /v1/traces - Receive OTLP trace data
- POST /v1/metrics - Receive OTLP metric data
- POST /v1/logs - Receive OTLP log data
- GET /health - Health check

Converts OTLP format → Insight API format and forwards:
- Traces → /api/v1/traces (span summaries) + /api/v1/events (error spans)
- Metrics → /api/v1/metrics (standard metric format)
- Logs → /api/v1/logs (log entries)
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

# OTLP Protobuf support
try:
    from google.protobuf.json_format import MessageToDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    HAS_PROTOBUF = True
except ImportError:
    HAS_PROTOBUF = False

# ─── Configuration ───

CORE_API_URL = os.getenv("INSIGHT_CORE_URL", "http://localhost:8080")
API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")
AGENT_ID = os.getenv("AGENT_ID", f"collector-{socket.gethostname()}")
AGENT_NAME = os.getenv("AGENT_NAME", f"Insight Collector ({socket.gethostname()})")
LISTEN_PORT = int(os.getenv("OTEL_PORT", "4318"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("insight.otel-agent")

# ─── FastAPI App ───

app = FastAPI(title="Insight OTLP Collector", version="5.0.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Stats
stats = {"traces_received": 0, "metrics_received": 0, "logs_received": 0, "spans_forwarded": 0, "errors": 0}


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


# ─── OTLP Data Parsing ───

async def _parse_otlp_request(request: Request, proto_class=None) -> dict:
    """Parse OTLP request body, supporting both protobuf and JSON formats."""
    content_type = request.headers.get("content-type", "")
    body = await request.body()

    if "protobuf" in content_type and HAS_PROTOBUF and proto_class:
        try:
            msg = proto_class()
            msg.ParseFromString(body)
            return MessageToDict(msg, preserving_proto_field_name=True)
        except Exception as e:
            logging.getLogger("insight.otel-agent").warning(f"Protobuf parse failed: {e}")
            return {}

    # Try JSON
    try:
        return json.loads(body)
    except Exception:
        return {}


# ─── OTLP Trace Processing ───

def _extract_spans(otlp_data: dict) -> list[dict]:
    """Extract span summaries from OTLP trace export request.
    Handles both camelCase (JSON) and snake_case (protobuf) field names.
    Composes rich span names from HTTP attributes when available.
    """
    spans = []
    resource_spans = otlp_data.get("resourceSpans", otlp_data.get("resource_spans", []))

    for rs in resource_spans:
        # Extract service name from resource attributes
        service_name = "unknown"
        resource = rs.get("resource", {})
        for attr in resource.get("attributes", []):
            if attr.get("key") == "service.name":
                val = attr.get("value", {})
                service_name = val.get("stringValue", val.get("string_value", "unknown"))
                break

        scope_spans = rs.get("scopeSpans", rs.get("scope_spans", []))
        for ss in scope_spans:
            for span in ss.get("spans", []):
                trace_id = span.get("traceId", span.get("trace_id", ""))
                span_id = span.get("spanId", span.get("span_id", str(uuid.uuid4())[:16]))
                span_name = span.get("name", "")
                kind = span.get("kind", 0)

                # Calculate duration
                start_ns = int(span.get("startTimeUnixNano", span.get("start_time_unix_nano", 0)))
                end_ns = int(span.get("endTimeUnixNano", span.get("end_time_unix_nano", 0)))
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
                    attrs[key] = (val.get("stringValue") or val.get("string_value")
                                  or val.get("intValue") or val.get("int_value")
                                  or val.get("doubleValue") or val.get("double_value")
                                  or val.get("boolValue") or val.get("bool_value", ""))

                # Compose rich span name from HTTP attributes
                http_method = attrs.get("http.request.method") or attrs.get("http.method", "")
                http_route = attrs.get("http.route") or attrs.get("url.path") or attrs.get("http.target", "")
                if http_method and http_route:
                    span_name = f"{http_method} {http_route}"
                elif http_method and span_name in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                    # Keep original if it already has method, otherwise enrich
                    pass

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
    """Extract metrics from OTLP metric export request.
    Handles both camelCase (JSON) and snake_case (protobuf) field names.
    """
    metrics = []
    resource_metrics = otlp_data.get("resourceMetrics", otlp_data.get("resource_metrics", []))

    for rm in resource_metrics:
        # Extract host/service labels
        labels = {}
        resource = rm.get("resource", {})
        for attr in resource.get("attributes", []):
            key = attr.get("key", "")
            val = attr.get("value", {})
            value = (val.get("stringValue") or val.get("string_value")
                     or val.get("intValue") or val.get("int_value")
                     or val.get("doubleValue") or val.get("double_value", ""))
            if key in ("host.name", "service.name", "service.namespace"):
                labels[key.replace(".", "_")] = value

        scope_metrics = rm.get("scopeMetrics", rm.get("scope_metrics", []))
        for sm in scope_metrics:
            for metric in sm.get("metrics", []):
                name = metric.get("name", "")
                unit = metric.get("unit", "")

                # Handle different metric data types
                data_points = []
                if "gauge" in metric:
                    data_points = metric["gauge"].get("dataPoints", metric["gauge"].get("data_points", []))
                elif "sum" in metric:
                    data_points = metric["sum"].get("dataPoints", metric["sum"].get("data_points", []))
                elif "histogram" in metric:
                    hist = metric["histogram"]
                    for dp in hist.get("dataPoints", hist.get("data_points", [])):
                        count = int(dp.get("count", 0) or 0)
                        total = float(dp.get("sum", 0) or 0)
                        avg = total / count if count > 0 else 0
                        metrics.append({
                            "metric_name": name,
                            "metric_value": avg,
                            "labels": {**labels, "unit": unit, "type": "histogram_avg"},
                        })
                    continue

                for dp in data_points:
                    value = dp.get("asDouble") or dp.get("as_double") or dp.get("asInt") or dp.get("as_int") or 0
                    metrics.append({
                        "metric_name": name,
                        "metric_value": float(value),
                        "labels": {**labels, "unit": unit},
                    })

    return metrics


# ─── HTTP Endpoints ───

@app.get("/health")
async def health():
    return {"status": "ok", "agent": AGENT_ID, "version": "6.0.0", "stats": stats}


@app.post("/v1/traces")
async def receive_traces(request: Request):
    """OTLP HTTP Trace Receiver (protobuf + JSON)."""
    proto_cls = ExportTraceServiceRequest if HAS_PROTOBUF else None
    data = await _parse_otlp_request(request, proto_cls)
    if not data:
        return {"partialSuccess": {"rejectedSpans": 0, "errorMessage": "parse error"}}

    spans = _extract_spans(data)
    stats["traces_received"] += 1
    stats["spans_forwarded"] += len(spans)
    logger.info(f"Received {len(spans)} spans (proto={HAS_PROTOBUF})")

    if spans:
        result = send_to_core("/api/v1/traces", {
            "agent_id": AGENT_ID,
            "traces": spans,
        })
        logger.info(f"Forwarded {len(spans)} traces → Core API: {'OK' if result else 'FAILED'}")

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
                "agent_category": "application",
                "hostname": socket.gethostname(),
                "events": events,
            })
            logger.info(f"Forwarded {len(events)} error events")

    return {"partialSuccess": {}}


@app.post("/v1/metrics")
async def receive_metrics(request: Request):
    """OTLP HTTP Metric Receiver (protobuf + JSON)."""
    proto_cls = ExportMetricsServiceRequest if HAS_PROTOBUF else None
    data = await _parse_otlp_request(request, proto_cls)
    if not data:
        return {"partialSuccess": {"rejectedDataPoints": 0, "errorMessage": "parse error"}}

    metrics = _extract_metrics(data)
    stats["metrics_received"] += 1
    logger.info(f"Received {len(metrics)} metrics (proto={HAS_PROTOBUF})")

    if metrics:
        send_to_core("/api/v1/metrics", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "opentelemetry",
            "agent_category": "application",
            "hostname": socket.gethostname(),
            "metrics": metrics,
        })

    return {"partialSuccess": {}}


@app.post("/v1/logs")
async def receive_logs(request: Request):
    """OTLP HTTP Log Receiver (protobuf + JSON)."""
    proto_cls = ExportLogsServiceRequest if HAS_PROTOBUF else None
    data = await _parse_otlp_request(request, proto_cls)
    if not data:
        return {"partialSuccess": {}}

    logs = []
    for rl in data.get("resourceLogs", data.get("resource_logs", [])):
        # Extract service name from resource
        svc_name = "otel"
        res = rl.get("resource", {})
        for attr in res.get("attributes", []):
            if attr.get("key") == "service.name":
                val = attr.get("value", {})
                svc_name = val.get("stringValue", val.get("string_value", "otel"))
                break

        for sl in rl.get("scopeLogs", rl.get("scope_logs", [])):
            for lr in sl.get("logRecords", sl.get("log_records", [])):
                severity = lr.get("severityText", lr.get("severity_text", "INFO")).upper()
                level = "critical" if severity in ("FATAL", "CRITICAL") else \
                        "error" if severity == "ERROR" else \
                        "warning" if ("WARN" in severity) else "info"
                body_field = lr.get("body", {})
                body = body_field.get("stringValue", body_field.get("string_value", ""))
                # Map to DB schema: log_level, namespace (as source), message
                logs.append({
                    "log_level": level,
                    "namespace": svc_name,
                    "pod_name": "",
                    "container": "",
                    "message": body[:500],
                })

    stats["logs_received"] += 1
    if logs:
        send_to_core("/api/v1/logs", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "opentelemetry",
            "agent_category": "application",
            "hostname": socket.gethostname(),
            "logs": logs,
        })
        logger.info(f"Forwarded {len(logs)} logs → Core API")

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
                "agent_type": "collector",
                "agent_category": "application",
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
    logger.info(f"Insight Collector v5.0.2 starting...")
    logger.info(f"   Agent ID: {AGENT_ID}")
    logger.info(f"   Core URL: {CORE_API_URL}")
    logger.info(f"   OTLP HTTP Port: {LISTEN_PORT}")

    # Start heartbeat thread
    t = Thread(target=_heartbeat_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
