"""
Insight Report Service - Generate and send monitoring reports.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("insight.report")


def generate_report(
    agents: list[dict],
    metrics_by_agent: dict[str, list[dict]],
    events: list[dict],
    logs: list[dict],
    report_type: str = "daily",
) -> dict:
    """Generate a comprehensive monitoring report."""
    now = datetime.now(timezone.utc)

    # Aggregate stats
    total_agents = len(agents)
    active_agents = sum(1 for a in agents if a.get("status") == "active")
    
    critical_events = [e for e in events if e.get("level") == "critical"]
    error_events = [e for e in events if e.get("level") == "error"]

    report = {
        "type": report_type,
        "generated_at": now.isoformat(),
        "summary": {
            "total_agents": total_agents,
            "active_agents": active_agents,
            "total_events": len(events),
            "critical_events": len(critical_events),
            "error_events": len(error_events),
            "total_error_logs": len(logs),
        },
        "agents": [],
        "critical_issues": [],
    }

    # Per-agent details
    for agent in agents:
        agent_id = agent.get("id", "")
        agent_metrics = metrics_by_agent.get(agent_id, [])

        agent_report = {
            "name": agent.get("name", ""),
            "type": agent.get("agent_type", ""),
            "status": agent.get("status", ""),
            "hostname": agent.get("hostname", ""),
            "metrics": {},
        }

        for m in agent_metrics:
            name = m.get("metric_name", "")
            value = m.get("metric_value", 0)
            labels = m.get("labels", {})
            agent_report["metrics"][name] = {
                "value": value,
                "labels": labels,
            }

        report["agents"].append(agent_report)

    # Critical issues
    for event in critical_events + error_events:
        report["critical_issues"].append({
            "level": event.get("level", ""),
            "title": event.get("title", ""),
            "message": event.get("message", ""),
            "source": event.get("source", ""),
            "time": event.get("created_at", ""),
        })

    return report


def format_report_telegram(report: dict) -> str:
    """Format report for Telegram (HTML)."""
    summary = report.get("summary", {})
    agents = report.get("agents", [])
    issues = report.get("critical_issues", [])
    generated = report.get("generated_at", "")

    lines = [
        "<b>📊 INSIGHT DAILY REPORT</b>",
        f"🕐 {generated[:19]}",
        "",
        "<b>— TỔNG QUAN —</b>",
        f"Agents: {summary.get('active_agents', 0)}/{summary.get('total_agents', 0)} active",
        f"Events: {summary.get('total_events', 0)} (🔴 {summary.get('critical_events', 0)} critical, ❌ {summary.get('error_events', 0)} error)",
        f"Error logs: {summary.get('total_error_logs', 0)}",
        "",
    ]

    # Agent details
    if agents:
        lines.append("<b>— AGENTS —</b>")
        for a in agents:
            status_icon = "✅" if a["status"] == "active" else "❌"
            lines.append(f"{status_icon} {a['name']} ({a['type']}) - {a['status']}")
            
            metrics = a.get("metrics", {})
            if "cpu_percent" in metrics:
                lines.append(f"  CPU: {metrics['cpu_percent']['value']:.1f}%")
            if "memory_percent" in metrics:
                lines.append(f"  RAM: {metrics['memory_percent']['value']:.1f}%")
            if "disk_percent" in metrics:
                lines.append(f"  Disk: {metrics['disk_percent']['value']:.1f}%")
        lines.append("")

    # Critical issues
    if issues:
        lines.append("<b>— SỰ CỐ —</b>")
        for issue in issues[:10]:  # Max 10 issues
            icon = "🔴" if issue["level"] == "critical" else "❌"
            lines.append(f"{icon} [{issue['level'].upper()}] {issue['title']}")
            if issue.get("message"):
                msg = issue["message"][:200]
                lines.append(f"  {msg}")
        lines.append("")

    if not issues:
        lines.append("✅ <b>Không có sự cố nghiêm trọng</b>")

    lines.append("<i>— Insight Monitoring System —</i>")
    return "\n".join(lines)


def format_report_email(report: dict) -> str:
    """Format report as HTML email."""
    summary = report.get("summary", {})
    agents = report.get("agents", [])
    issues = report.get("critical_issues", [])

    agent_rows = ""
    for a in agents:
        status_color = "#28a745" if a["status"] == "active" else "#dc3545"
        metrics = a.get("metrics", {})
        cpu = f"{metrics.get('cpu_percent', {}).get('value', 'N/A')}"
        ram = f"{metrics.get('memory_percent', {}).get('value', 'N/A')}"
        agent_rows += f"""
        <tr>
            <td>{a['name']}</td>
            <td>{a['type']}</td>
            <td style="color: {status_color}; font-weight: bold;">{a['status']}</td>
            <td>{cpu}%</td>
            <td>{ram}%</td>
        </tr>"""

    issue_rows = ""
    for issue in issues[:20]:
        level_color = "#dc3545" if issue["level"] == "critical" else "#fd7e14"
        issue_rows += f"""
        <tr>
            <td style="color: {level_color}; font-weight: bold;">{issue['level'].upper()}</td>
            <td>{issue['title']}</td>
            <td>{issue.get('message', '')[:100]}</td>
        </tr>"""

    return f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; padding: 20px;">
        <div style="max-width: 800px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px;">
                <h1 style="margin: 0;">📊 Insight Daily Report</h1>
                <p style="margin: 8px 0 0; opacity: 0.9;">{report.get('generated_at', '')[:19]}</p>
            </div>
            
            <div style="padding: 24px;">
                <h2>Tổng quan</h2>
                <div style="display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px;">
                    <div style="background: #e3f2fd; padding: 16px; border-radius: 8px; flex: 1; min-width: 120px; text-align: center;">
                        <div style="font-size: 24px; font-weight: bold;">{summary.get('active_agents', 0)}/{summary.get('total_agents', 0)}</div>
                        <div>Active Agents</div>
                    </div>
                    <div style="background: #fff3e0; padding: 16px; border-radius: 8px; flex: 1; min-width: 120px; text-align: center;">
                        <div style="font-size: 24px; font-weight: bold;">{summary.get('total_events', 0)}</div>
                        <div>Events</div>
                    </div>
                    <div style="background: #fce4ec; padding: 16px; border-radius: 8px; flex: 1; min-width: 120px; text-align: center;">
                        <div style="font-size: 24px; font-weight: bold; color: #dc3545;">{summary.get('critical_events', 0)}</div>
                        <div>Critical</div>
                    </div>
                </div>

                <h2>Agents</h2>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
                    <tr style="background: #f8f9fa;">
                        <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Name</th>
                        <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Type</th>
                        <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Status</th>
                        <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">CPU</th>
                        <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">RAM</th>
                    </tr>
                    {agent_rows}
                </table>

                {"<h2>Sự cố</h2><table style='width:100%;border-collapse:collapse;'><tr style='background:#f8f9fa;'><th style='padding:8px;text-align:left;border-bottom:2px solid #dee2e6;'>Level</th><th style='padding:8px;text-align:left;border-bottom:2px solid #dee2e6;'>Title</th><th style='padding:8px;text-align:left;border-bottom:2px solid #dee2e6;'>Message</th></tr>" + issue_rows + "</table>" if issues else "<p style='color: #28a745; font-weight: bold;'>✅ Không có sự cố nghiêm trọng</p>"}
            </div>
            
            <div style="background: #f8f9fa; padding: 16px; text-align: center; color: #666; font-size: 12px;">
                Insight Monitoring System
            </div>
        </div>
    </body>
    </html>
    """
