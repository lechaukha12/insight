"""
Insight MCP Server — Tool-based monitoring data access for Gemini.
Only this module may query the database for AI chat context.
Uses Gemini Automatic Function Calling (AFC) so the model decides
which tools to invoke based on the user's question.
"""

import json
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("insight.mcp")

# ═══════════════════════════════════════════════════════════
# MCP Tools — each function is a tool Gemini can call
# ═══════════════════════════════════════════════════════════

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
            "os": a.get("os_name", ""),
            "ip": a.get("ip_address", ""),
            "last_heartbeat": str(a.get("last_heartbeat", "")),
        }
        for a in agents[:30]
    ]


def get_system_metrics() -> list[dict]:
    """Get latest system metrics (CPU, RAM, Disk usage) per agent.
    Returns a list with hostname and their current resource usage percentages."""
    from shared.database.db import get_latest_metrics_per_agent
    raw = get_latest_metrics_per_agent() or {}
    results = []
    for agent_id, metrics in list(raw.items())[:15]:
        entry = {"agent_id": agent_id}
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


def get_recent_events(severity: str = "", limit: int = 10) -> list[dict]:
    """Get recent monitoring events from the last 24 hours.
    Args:
        severity: Filter by severity level (critical, warning, info). Empty for all.
        limit: Maximum number of events to return (default 10, max 20).
    Returns a list of event objects with title, severity, source, and timestamp."""
    from shared.database.db import get_events
    limit = min(limit, 20)
    events = get_events(level=severity or None, limit=limit) or []
    return [
        {
            "title": e.get("title", ""),
            "severity": e.get("severity", ""),
            "source": e.get("source", ""),
            "message": str(e.get("message", ""))[:200],
            "timestamp": str(e.get("timestamp", "")),
        }
        for e in events
    ]


def get_error_logs(limit: int = 10) -> list[dict]:
    """Get recent error-level logs from all sources.
    Args:
        limit: Maximum number of logs to return (default 10, max 20).
    Returns a list of log entries with source, message, severity, and timestamp."""
    from shared.database.db import get_logs
    limit = min(limit, 20)
    logs = get_logs(log_level="error", limit=limit) or []
    return [
        {
            "source": l.get("source", ""),
            "message": str(l.get("message", ""))[:300],
            "severity": l.get("severity", l.get("log_level", "")),
            "timestamp": str(l.get("timestamp", "")),
        }
        for l in logs
    ]


def get_trace_overview(last_hours: int = 24) -> dict:
    """Get distributed tracing summary including total spans, error spans, and per-service breakdown.
    Args:
        last_hours: Look back period in hours (default 24, max 168).
    Returns a summary with total_spans, error_spans, and a services list with span counts and average duration."""
    from shared.database.db import get_trace_summary
    last_hours = min(last_hours, 168)
    summary = get_trace_summary(last_hours=last_hours) or {}
    services = []
    for svc in (summary.get("services", []) or [])[:15]:
        services.append({
            "service_name": svc.get("service_name", ""),
            "span_count": svc.get("span_count", 0),
            "avg_duration_ms": round(svc.get("avg_duration_ms", 0), 1),
            "error_count": svc.get("error_count", 0),
        })
    return {
        "total_spans": summary.get("total_spans", 0),
        "error_spans": summary.get("error_spans", 0),
        "services": services,
    }


def get_application_services() -> list[dict]:
    """Get list of application services detected from OpenTelemetry traces.
    Returns a list of services with name, span count, and error rate."""
    from shared.database.db import get_services
    services = get_services(last_hours=24) or []
    return [
        {
            "service_name": s.get("service_name", ""),
            "span_count": s.get("span_count", 0),
            "error_count": s.get("error_count", 0),
            "avg_duration_ms": round(s.get("avg_duration_ms", 0), 1),
        }
        for s in services[:20]
    ]


# ═══════════════════════════════════════════════════════════
# MCP Server — orchestrates Gemini + tools
# ═══════════════════════════════════════════════════════════

MCP_TOOLS = [
    get_system_agents,
    get_system_metrics,
    get_recent_events,
    get_error_logs,
    get_trace_overview,
    get_application_services,
]

SYSTEM_PROMPT = """Bạn là Insight AI Assistant — trợ lý giám sát hệ thống thông minh.
Bạn có các công cụ (tools) để truy vấn dữ liệu monitoring realtime.
Hãy sử dụng tools phù hợp để lấy dữ liệu trước khi trả lời.
Trả lời câu hỏi của admin bằng tiếng Việt.
Nếu phát hiện vấn đề, hãy đề xuất giải pháp cụ thể.
Trả lời ngắn gọn, chuyên nghiệp, sử dụng markdown formatting.
Đừng lặp lại toàn bộ dữ liệu thô — chỉ trích dẫn phần liên quan.
Nếu user hỏi chung chung về hệ thống, hãy gọi nhiều tools để có cái nhìn tổng quan."""


async def chat(api_key: str, model_name: str, user_message: str, history: list[dict] = None) -> str:
    """Process a chat message using Gemini with MCP tools (function calling).
    
    Args:
        api_key: Gemini API key
        model_name: Gemini model to use
        user_message: The user's message
        history: Previous conversation history
    
    Returns:
        The AI assistant's response text
    """
    client = genai.Client(api_key=api_key)

    # Build conversation contents
    contents = []
    for h in (history or [])[-10:]:
        role = h.get("role", "user")
        if role == "model":
            role = "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=h.get("content", ""))]
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)]
    ))

    # Configure with tools for function calling
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=MCP_TOOLS,
        temperature=0.7,
        max_output_tokens=2048,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=False,
            maximum_remote_calls=5,
        ),
    )

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )

    return response.text or "Không thể xử lý yêu cầu."
