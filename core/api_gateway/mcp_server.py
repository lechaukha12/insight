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


# ═══════════════════════════════════════════════════════════
# MCP Server — orchestrates Gemini + tools
# ═══════════════════════════════════════════════════════════

MCP_TOOLS = [
    # Agents & Metrics
    get_system_agents,
    get_agent_detail,
    get_system_metrics,
    get_process_list,
    # Events
    get_recent_events,
    get_event_counts,
    get_event_timeline,
    # Logs (stats only)
    get_log_stats,
    get_error_logs,
    # Traces & Services
    get_trace_overview,
    get_application_services,
    # Infrastructure
    get_clusters,
    get_storage_info,
    # Configuration
    get_notification_rules,
    get_alert_channels,
    get_webhooks_summary,
]

# Tools to auto-call for context gathering (lightweight ones only)
CONTEXT_TOOLS = [
    get_system_agents,
    get_system_metrics,
    get_event_counts,
    get_recent_events,
    get_log_stats,
    get_error_logs,
    get_trace_overview,
    get_application_services,
    get_clusters,
    get_notification_rules,
    get_alert_channels,
    get_webhooks_summary,
    get_storage_info,
]

SYSTEM_PROMPT = """Bạn là Insight AI Assistant — trợ lý giám sát hệ thống thông minh.
Dữ liệu monitoring realtime được cung cấp bên dưới qua MCP Server (16 tools).
Trả lời câu hỏi của admin bằng tiếng Việt.
Nếu phát hiện vấn đề, hãy đề xuất giải pháp cụ thể.
Trả lời ngắn gọn, chuyên nghiệp, sử dụng markdown formatting.
Đừng lặp lại toàn bộ dữ liệu thô — chỉ trích dẫn phần liên quan.
Nếu user hỏi chung chung về hệ thống, hãy tổng hợp từ nhiều nguồn dữ liệu.
Các tool có sẵn: agents, metrics, events, logs (stats), traces, services, clusters, storage, rules, alerts, webhooks, processes."""


async def chat(api_key: str, model_name: str, user_message: str, history: list[dict] = None) -> str:
    """Process a chat message using Gemini with MCP tools (context-gathering approach)."""
    client = genai.Client(api_key=api_key)

    # Build conversation contents
    contents = []
    for h in (history or [])[-10:]:
        role = h.get("role", "user")
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=h.get("content", ""))]
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)]
    ))

    # Gather monitoring context via MCP tools
    context_parts = []
    for fn in CONTEXT_TOOLS:
        try:
            if fn.__name__ == "get_recent_events":
                data = fn(severity="", limit=10)
            elif fn.__name__ == "get_error_logs":
                data = fn(limit=10)
            elif fn.__name__ == "get_trace_overview":
                data = fn(last_hours=24)
            elif fn.__name__ == "get_event_timeline":
                data = fn(last_hours=24)
            else:
                data = fn()
            context_parts.append(f"[{fn.__name__}]: {json.dumps(data, ensure_ascii=False, default=str)[:2000]}")
            logger.info(f"MCP tool executed: {fn.__name__}")
        except Exception as e:
            logger.warning(f"MCP tool {fn.__name__} failed: {e}")
            context_parts.append(f"[{fn.__name__}]: error - {e}")

    monitoring_context = "\n".join(context_parts)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT + "\n\nMONITORING DATA (via MCP Server):\n" + monitoring_context,
        temperature=0.7,
        max_output_tokens=2048,
    )

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )

    return response.text or "Không thể xử lý yêu cầu."
