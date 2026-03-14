"""
Insight MCP Server — Tool-based monitoring data access for Gemini.
Only this module may query the database for AI chat context.
Uses context-gathering approach: all tools run first, data injected as context.
16 tools covering: agents, metrics, events, logs, traces, services,
clusters, alerts, storage, processes, webhooks.
"""

import json
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("insight.mcp")

# ═══════════════════════════════════════════════════════════
# MCP Tools — each function is a tool Gemini can call
# ═══════════════════════════════════════════════════════════

# ──── 1. Agents ────

def get_system_agents() -> list[dict]:
    """Get all monitoring agents with their status, hostname, type, category, OS, and IP.
    Returns a list of agent objects with fields: hostname, status, agent_type, agent_category, os, ip, last_heartbeat."""
    from shared.database.db import list_agents
    agents = list_agents() or []
    return [
        {
            "hostname": a.get("hostname", ""),
            "status": a.get("status", ""),
            "agent_type": a.get("agent_type", ""),
            "agent_category": a.get("agent_category", ""),
            "os": a.get("os_name", "") or a.get("os_info", ""),
            "ip": a.get("ip_address", ""),
            "cluster_id": a.get("cluster_id", ""),
            "agent_version": a.get("agent_version", ""),
            "last_heartbeat": str(a.get("last_heartbeat", "")),
        }
        for a in agents[:30]
    ]


def get_agent_detail(hostname: str) -> dict:
    """Get detailed info about a specific agent by hostname.
    Args:
        hostname: The hostname of the agent to look up.
    Returns agent details including OS, IP, version, labels, status, and last heartbeat."""
    from shared.database.db import list_agents
    agents = list_agents() or []
    for a in agents:
        if a.get("hostname", "") == hostname or a.get("name", "") == hostname:
            labels = a.get("labels", {})
            if isinstance(labels, str):
                try:
                    labels = json.loads(labels)
                except Exception:
                    labels = {}
            return {
                "hostname": a.get("hostname", ""),
                "name": a.get("name", ""),
                "status": a.get("status", ""),
                "agent_type": a.get("agent_type", ""),
                "agent_category": a.get("agent_category", ""),
                "os_info": a.get("os_info", ""),
                "ip_address": a.get("ip_address", ""),
                "agent_version": a.get("agent_version", ""),
                "cluster_id": a.get("cluster_id", ""),
                "labels": labels,
                "last_heartbeat": str(a.get("last_heartbeat", "")),
                "created_at": str(a.get("created_at", "")),
            }
    return {"error": f"Agent '{hostname}' not found"}


# ──── 2. Metrics ────

def get_system_metrics() -> list[dict]:
    """Get latest system metrics (CPU, RAM, Disk usage) per agent.
    Returns a list with hostname and their current resource usage percentages."""
    from shared.database.db import get_latest_metrics_per_agent, list_agents
    raw = get_latest_metrics_per_agent() or {}
    agents = {a.get("id", ""): a.get("hostname", "") for a in (list_agents() or [])}
    results = []
    for agent_id, metrics in list(raw.items())[:15]:
        entry = {"agent_id": agent_id, "hostname": agents.get(agent_id, agent_id)}
        for m in metrics:
            name = m.get("metric_name", "")
            if "cpu" in name.lower():
                entry["cpu_percent"] = round(m.get("metric_value", 0), 1)
            elif "memory" in name.lower() or "ram" in name.lower():
                entry["memory_percent"] = round(m.get("metric_value", 0), 1)
            elif "disk" in name.lower():
                entry["disk_percent"] = round(m.get("metric_value", 0), 1)
        results.append(entry)
    return results


# ──── 3. Events ────

def get_recent_events(severity: str, limit: int) -> list[dict]:
    """Get recent monitoring events from the last 24 hours.
    Args:
        severity: Filter by severity level (critical, warning, info). Use empty string for all.
        limit: Maximum number of events to return. Use 10 for default, max 20.
    Returns a list of event objects with title, severity, source, and timestamp."""
    from shared.database.db import get_events
    limit = min(limit or 10, 20)
    events = get_events(level=severity or None, limit=limit) or []
    return [
        {
            "title": e.get("title", ""),
            "severity": e.get("severity", "") or e.get("level", ""),
            "source": e.get("source", ""),
            "message": str(e.get("message", ""))[:200],
            "timestamp": str(e.get("timestamp", "") or e.get("created_at", "")),
        }
        for e in events
    ]


def get_event_counts() -> dict:
    """Get event count summary grouped by severity level for the last 24 hours.
    Returns a dictionary with keys: critical, error, warning, info, and total."""
    from shared.database.db import get_event_counts as _get_event_counts
    counts = _get_event_counts(last_hours=24) or {}
    total = sum(counts.values())
    return {
        "critical": counts.get("critical", 0),
        "error": counts.get("error", 0),
        "warning": counts.get("warning", 0),
        "info": counts.get("info", 0),
        "total": total,
    }


def get_event_timeline(last_hours: int) -> list[dict]:
    """Get event counts per hour for trend analysis.
    Args:
        last_hours: Look back period in hours. Use 24 for default, max 72.
    Returns a list of hourly buckets with counts per severity level."""
    from shared.database.db import get_event_counts_by_hour
    last_hours = min(last_hours or 24, 72)
    return get_event_counts_by_hour(last_hours=last_hours) or []


# ──── 4. Logs (stats only — NO raw messages) ────

def get_log_stats() -> dict:
    """Get log statistics: count of logs per severity level and per source in the last 24 hours.
    Does NOT return raw log messages for security reasons.
    Returns summary with total_logs, severity_counts, and top_sources."""
    from shared.database.db import get_logs
    all_logs = get_logs(limit=500) or []
    severity_counts = {}
    source_counts = {}
    for l in all_logs:
        level = l.get("log_level", "unknown").lower()
        severity_counts[level] = severity_counts.get(level, 0) + 1
        source = l.get("agent_id", "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    # Top sources
    top_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "total_logs": len(all_logs),
        "severity_counts": severity_counts,
        "top_sources": [{"agent_id": s[0], "count": s[1]} for s in top_sources],
    }


def get_error_logs(limit: int) -> list[dict]:
    """Get recent error-level log entries (metadata only, messages are truncated for security).
    Args:
        limit: Maximum number of logs to return. Use 10 for default, max 20.
    Returns a list of log entries with source, severity, pod, namespace, and timestamp. No raw messages."""
    from shared.database.db import get_logs
    limit = min(limit or 10, 20)
    all_logs = get_logs(limit=200) or []
    error_logs = [l for l in all_logs if l.get("log_level", "").lower() in ("error", "critical", "fatal")]
    return [
        {
            "agent_id": l.get("agent_id", ""),
            "severity": l.get("log_level", ""),
            "namespace": l.get("namespace", ""),
            "pod_name": l.get("pod_name", ""),
            "container": l.get("container", ""),
            "timestamp": str(l.get("timestamp", "")),
        }
        for l in error_logs[:limit]
    ]


# ──── 5. Traces & Services ────

def get_trace_overview(last_hours: int) -> dict:
    """Get distributed tracing summary including total spans, error spans, and per-service breakdown.
    Args:
        last_hours: Look back period in hours. Use 24 for default, max 168.
    Returns a summary with total_requests, error_count, error_rate, avg_latency, and services list."""
    from shared.database.db import get_trace_summary
    last_hours = min(last_hours or 24, 168)
    summary = get_trace_summary(last_hours=last_hours) or {}
    services = []
    for svc in (summary.get("services", []) or [])[:15]:
        services.append({
            "service_name": svc.get("name", svc.get("service_name", "")),
            "requests": svc.get("requests", svc.get("span_count", 0)),
            "avg_latency_ms": round(svc.get("avg_latency_ms", 0), 1),
            "p95_latency_ms": round(svc.get("p95_latency_ms", 0), 1),
            "error_count": svc.get("error_count", 0),
            "error_rate": round(svc.get("error_rate", 0), 2),
        })
    return {
        "total_requests": summary.get("total_requests", 0),
        "error_count": summary.get("error_count", 0),
        "error_rate": summary.get("error_rate", 0),
        "avg_latency_ms": summary.get("avg_latency_ms", 0),
        "services": services,
    }


def get_application_services() -> list[dict]:
    """Get list of application services detected from OpenTelemetry traces.
    Returns a list of services with name, request count, error count, and average latency."""
    from shared.database.db import get_services
    services = get_services(last_hours=24) or []
    return [
        {
            "service_name": s.get("service_name", ""),
            "request_count": s.get("req_count", 0),
            "error_count": s.get("error_count", 0),
            "avg_latency_ms": round(s.get("avg_latency", s.get("avg_duration_ms", 0)), 1),
            "last_seen": str(s.get("last_seen", "")),
        }
        for s in services[:20]
    ]


# ──── 6. Clusters ────

def get_clusters() -> list[dict]:
    """Get all registered monitoring clusters.
    Returns a list of clusters with id, name, description, status, and agent count."""
    from shared.database.db import list_clusters, list_agents
    clusters = list_clusters() or []
    agents = list_agents() or []
    # Count agents per cluster
    cluster_agent_count = {}
    for a in agents:
        cid = a.get("cluster_id", "default")
        cluster_agent_count[cid] = cluster_agent_count.get(cid, 0) + 1
    return [
        {
            "id": c.get("id", ""),
            "name": c.get("name", ""),
            "description": c.get("description", ""),
            "status": c.get("status", ""),
            "agent_count": cluster_agent_count.get(c.get("id", ""), 0),
        }
        for c in clusters
    ]


# ──── 7. Notification Rules ────

def get_notification_rules() -> list[dict]:
    """Get all configured notification/alert rules.
    Returns rules with name, metric, operator, threshold, channels, and enabled status."""
    from shared.database.db import get_rules
    rules = get_rules() or []
    return [
        {
            "name": r.get("name", ""),
            "metric_name": r.get("metric_name", ""),
            "operator": r.get("operator", ">"),
            "threshold": r.get("threshold", 0),
            "duration_minutes": r.get("duration_minutes", 5),
            "channels": r.get("channels", []),
            "enabled": r.get("enabled", False),
        }
        for r in rules[:20]
    ]


# ──── 8. Alert Configs (masked) ────

def get_alert_channels() -> list[dict]:
    """Get configured alert notification channels (Telegram, Email, etc).
    Returns channel type, enabled status, and alert levels. Sensitive config data is masked."""
    from shared.database.db import get_alert_configs
    configs = get_alert_configs() or []
    return [
        {
            "channel": c.get("channel", ""),
            "enabled": c.get("enabled", False),
            "alert_levels": c.get("alert_levels", []),
            "has_config": bool(c.get("config")),
        }
        for c in configs
    ]


# ──── 9. Storage Stats ────

def get_storage_info() -> dict:
    """Get database storage statistics per table including size, row count, and retention policy.
    Returns tables with name, size, rows, oldest/newest data, and retention days."""
    from shared.database.db import get_storage_stats
    stats = get_storage_stats() or {}
    tables = stats.get("tables", [])
    return {
        "engine": stats.get("engine", "clickhouse"),
        "tables": [
            {
                "name": t.get("name", ""),
                "size": t.get("size", "0 B"),
                "rows": t.get("rows", 0),
                "oldest_data": str(t.get("oldest", "")),
                "newest_data": str(t.get("newest", "")),
                "retention_days": t.get("retention_days"),
            }
            for t in tables[:20]
        ],
    }


# ──── 10. Process List ────

def get_process_list(hostname: str) -> dict:
    """Get top running processes (by CPU/RAM usage) for a specific agent.
    Args:
        hostname: The hostname of the agent to get processes for.
    Returns top 10 processes with name, CPU%, and memory usage."""
    from shared.database.db import list_agents, get_process_snapshot
    agents = list_agents() or []
    agent_id = None
    for a in agents:
        if a.get("hostname", "") == hostname or a.get("name", "") == hostname:
            agent_id = a.get("id")
            break
    if not agent_id:
        return {"error": f"Agent '{hostname}' not found", "processes": []}
    snapshot = get_process_snapshot(agent_id) or {}
    processes = snapshot.get("processes", [])
    # Return top 10 by CPU
    top = sorted(processes, key=lambda p: p.get("cpu_percent", 0), reverse=True)[:10]
    return {
        "hostname": hostname,
        "timestamp": str(snapshot.get("timestamp", "")),
        "top_processes": [
            {
                "name": p.get("name", ""),
                "pid": p.get("pid", 0),
                "cpu_percent": round(p.get("cpu_percent", 0), 1),
                "memory_mb": round(p.get("memory_mb", p.get("rss_mb", 0)), 1),
            }
            for p in top
        ],
    }


# ──── 11. Webhooks (masked URLs) ────

def get_webhooks_summary() -> list[dict]:
    """Get configured webhooks summary. URLs are masked for security.
    Returns list of webhooks with name, type, events, and enabled status."""
    from shared.database.db import get_webhooks
    webhooks = get_webhooks() or []
    return [
        {
            "name": w.get("name", ""),
            "type": w.get("type", "custom"),
            "events": w.get("events", []),
            "enabled": w.get("enabled", False),
            "has_url": bool(w.get("url")),
        }
        for w in webhooks[:20]
    ]


# ──── 12. Kubernetes Resources ────

def get_k8s_pod_detail_mcp(namespace: str, pod_name: str) -> dict:
    """Get detailed info about a specific Kubernetes pod including containers, status, conditions, events, and resource usage.
    Args:
        namespace: The Kubernetes namespace of the pod.
        pod_name: The name of the pod to inspect.
    Returns pod details with containers, ports, state, restart count, conditions, and events."""
    try:
        from api_gateway.k8s_resources import get_k8s_pod_detail
        return get_k8s_pod_detail(namespace, pod_name)
    except Exception as e:
        return {"error": str(e)}


def get_k8s_pod_logs_mcp(namespace: str, pod_name: str, tail_lines: int) -> dict:
    """Get the last N lines of logs from a Kubernetes pod.
    Args:
        namespace: The Kubernetes namespace of the pod.
        pod_name: The name of the pod to get logs from.
        tail_lines: Number of log lines to return (default 50, max 200).
    Returns log lines from the pod container."""
    try:
        from api_gateway.k8s_resources import get_k8s_pod_logs
        tail_lines = min(tail_lines or 50, 200)
        result = get_k8s_pod_logs(namespace, pod_name, tail_lines=tail_lines)
        # Truncate to avoid huge payloads
        if "lines" in result and len(result["lines"]) > 50:
            result["lines"] = result["lines"][-50:]
            result["truncated"] = True
        return result
    except Exception as e:
        return {"error": str(e)}


def get_k8s_configmaps_mcp(namespace: str) -> list:
    """Get list of ConfigMaps in a Kubernetes namespace.
    Args:
        namespace: The Kubernetes namespace. Use '_all' for all namespaces.
    Returns a list of ConfigMap names with namespace and age."""
    try:
        from api_gateway.k8s_resources import get_k8s_configmaps
        ns = None if namespace == "_all" else namespace
        return get_k8s_configmaps(ns)
    except Exception as e:
        return [{"error": str(e)}]


def get_k8s_configmap_detail_mcp(namespace: str, configmap_name: str) -> dict:
    """Get the content/data of a specific ConfigMap.
    Args:
        namespace: The Kubernetes namespace of the ConfigMap.
        configmap_name: Name of the ConfigMap to inspect.
    Returns the ConfigMap data (key-value pairs), labels, and age."""
    try:
        from api_gateway.k8s_resources import get_k8s_configmap_detail
        result = get_k8s_configmap_detail(namespace, configmap_name)
        # Truncate large values
        if "data" in result:
            for k, v in result["data"].items():
                if len(str(v)) > 500:
                    result["data"][k] = str(v)[:500] + "...(truncated)"
        return result
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# MCP Server — orchestrates Gemini + tools
# Token optimization: cache + smart routing + compression
# ═══════════════════════════════════════════════════════════

import re
import time
import os

MCP_TOOLS = [
    get_system_agents, get_agent_detail, get_system_metrics, get_process_list,
    get_recent_events, get_event_counts, get_event_timeline,
    get_log_stats, get_error_logs,
    get_trace_overview, get_application_services,
    get_clusters, get_storage_info,
    get_notification_rules, get_alert_channels, get_webhooks_summary,
    get_k8s_pod_detail_mcp, get_k8s_pod_logs_mcp,
    get_k8s_configmaps_mcp, get_k8s_configmap_detail_mcp,
]

# ─── Tool Groups for Smart Context Routing ───
# Maps keyword patterns → which tools to call
TOOL_ROUTING = {
    "core": [get_system_agents, get_system_metrics, get_event_counts],
    "agent": [get_system_agents, get_agent_detail, get_system_metrics],
    "metric": [get_system_metrics, get_system_agents],
    "cpu|ram|memory|disk|resource": [get_system_metrics, get_process_list],
    "event|alert|cảnh báo|sự cố|lỗi|error|critical": [get_event_counts, get_recent_events],
    "log": [get_log_stats, get_error_logs],
    "trace|tracing|latency|độ trễ|span": [get_trace_overview, get_application_services],
    "service|ứng dụng|app": [get_application_services, get_trace_overview],
    "cluster|cụm": [get_clusters],
    "storage|lưu trữ|dung lượng|database": [get_storage_info],
    "rule|notification|thông báo|quy tắc": [get_notification_rules, get_alert_channels],
    "webhook": [get_webhooks_summary],
    "process|tiến trình": [get_process_list],
    "pod|container|k8s|kubernetes": [get_k8s_pod_detail_mcp, get_k8s_pod_logs_mcp],
    "configmap|config map|cấu hình": [get_k8s_configmaps_mcp, get_k8s_configmap_detail_mcp],
    "overview": [
        get_system_agents, get_system_metrics, get_event_counts, get_recent_events,
        get_trace_overview, get_application_services,
    ],
}

# ─── In-Memory Cache (TTL-based) ───
_tool_cache: dict[str, tuple[float, any]] = {}
CACHE_TTL = int(os.getenv("MCP_CACHE_TTL", "60"))


def _cache_key(fn_name: str, *args, **kwargs) -> str:
    return f"{fn_name}:{json.dumps(args, default=str)}:{json.dumps(kwargs, default=str, sort_keys=True)}"


def _cached_call(fn, *args, **kwargs):
    """Call a tool function with TTL cache."""
    key = _cache_key(fn.__name__, *args, **kwargs)
    now = time.time()
    if key in _tool_cache:
        ts, data = _tool_cache[key]
        if now - ts < CACHE_TTL:
            logger.debug(f"Cache HIT: {fn.__name__}")
            return data, True
    data = fn(*args, **kwargs)
    _tool_cache[key] = (now, data)
    # Evict old entries
    cutoff = now - CACHE_TTL * 2
    for k in list(_tool_cache):
        if _tool_cache[k][0] < cutoff:
            del _tool_cache[k]
    return data, False


def _select_tools(user_message: str) -> list:
    """Smart routing: select tools based on user message keywords."""
    msg_lower = user_message.lower()
    selected = set()

    # Always include core tools
    for fn in TOOL_ROUTING["core"]:
        selected.add(fn.__name__)

    # Match keyword patterns
    for pattern, tools in TOOL_ROUTING.items():
        if pattern == "core":
            continue
        keywords = pattern.split("|")
        if any(kw in msg_lower for kw in keywords):
            for fn in tools:
                selected.add(fn.__name__)

    # If nothing specific matched, include overview set
    if len(selected) <= 3:
        for fn in TOOL_ROUTING.get("overview", []):
            selected.add(fn.__name__)

    fn_map = {fn.__name__: fn for fn in MCP_TOOLS}
    return [fn_map[name] for name in selected if name in fn_map]


def _compress_data(data, max_chars: int = 1500) -> str:
    """Compress tool output to reduce tokens."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    if isinstance(data, list) and len(data) > 5:
        data = data[:5]
        text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + "...]"
    return text


SYSTEM_PROMPT = """Bạn là Insight AI Assistant — trợ lý giám sát hệ thống thông minh.
Dữ liệu monitoring realtime được cung cấp bên dưới qua MCP Server.
Trả lời câu hỏi của admin bằng tiếng Việt.
Nếu phát hiện vấn đề, hãy đề xuất giải pháp cụ thể.
Trả lời ngắn gọn, chuyên nghiệp, sử dụng markdown formatting.
Đừng lặp lại toàn bộ dữ liệu thô — chỉ trích dẫn phần liên quan."""


async def chat(api_key: str, model_name: str, user_message: str, history: list[dict] = None) -> str:
    """Process a chat message using Gemini with optimized MCP tools.

    Optimizations:
    1. Smart routing: only calls tools relevant to the question
    2. TTL cache: reuses tool results within 60s window
    3. Data compression: limits JSON payload size
    """
    client = genai.Client(api_key=api_key)

    # Build conversation contents (limit history to last 6 to save tokens)
    contents = []
    for h in (history or [])[-6:]:
        role = h.get("role", "user")
        text = h.get("content", "")
        if len(text) > 500:
            text = text[:500] + "..."
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=text)]
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)]
    ))

    # Smart routing: select relevant tools only
    selected_tools = _select_tools(user_message)
    logger.info(f"Smart routing: {len(selected_tools)}/{len(MCP_TOOLS)} tools for '{user_message[:50]}'")

    # Gather context with caching
    context_parts = []
    cache_hits = 0
    for fn in selected_tools:
        try:
            if fn.__name__ == "get_recent_events":
                data, cached = _cached_call(fn, severity="", limit=8)
            elif fn.__name__ == "get_error_logs":
                data, cached = _cached_call(fn, limit=8)
            elif fn.__name__ == "get_trace_overview":
                data, cached = _cached_call(fn, last_hours=24)
            elif fn.__name__ == "get_event_timeline":
                data, cached = _cached_call(fn, last_hours=24)
            else:
                data, cached = _cached_call(fn)

            if cached:
                cache_hits += 1

            compressed = _compress_data(data)
            context_parts.append(f"[{fn.__name__}]: {compressed}")
        except Exception as e:
            logger.warning(f"MCP tool {fn.__name__} failed: {e}")

    total_chars = sum(len(p) for p in context_parts)
    logger.info(f"Context: {len(selected_tools)} tools, {cache_hits} cache hits, {total_chars} chars")

    monitoring_context = "\n".join(context_parts)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT + "\n\nMONITORING DATA:\n" + monitoring_context,
        temperature=0.7,
        max_output_tokens=1500,
    )

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )

    return response.text or "Không thể xử lý yêu cầu."

