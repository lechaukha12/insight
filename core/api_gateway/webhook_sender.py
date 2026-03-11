"""
Insight Monitoring System - Webhook Sender v5.0.0
Sends alerts to Slack, Discord, and custom webhook URLs.
"""

import json
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("insight.webhooks")

SLACK_COLORS = {"critical": "#991b1b", "error": "#dc2626", "warning": "#f59e0b", "info": "#0165a7"}
DISCORD_COLORS = {"critical": 0x991b1b, "error": 0xdc2626, "warning": 0xf59e0b, "info": 0x0165a7}


async def send_slack(url: str, level: str, title: str, message: str, source: str = "") -> bool:
    """Send alert to Slack incoming webhook."""
    payload = {
        "attachments": [{
            "color": SLACK_COLORS.get(level, "#666"),
            "title": f"[{level.upper()}] {title}",
            "text": message,
            "fields": [
                {"title": "Source", "value": source or "insight", "short": True},
                {"title": "Time", "value": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"), "short": True},
            ],
            "footer": "Insight Monitoring System",
        }]
    }
    return await _post(url, payload)


async def send_discord(url: str, level: str, title: str, message: str, source: str = "") -> bool:
    """Send alert to Discord webhook."""
    payload = {
        "embeds": [{
            "title": f"[{level.upper()}] {title}",
            "description": message,
            "color": DISCORD_COLORS.get(level, 0x666666),
            "fields": [
                {"name": "Source", "value": source or "insight", "inline": True},
                {"name": "Level", "value": level.upper(), "inline": True},
            ],
            "footer": {"text": "Insight Monitoring System"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    return await _post(url, payload)


async def send_custom(url: str, level: str, title: str, message: str, source: str = "") -> bool:
    """Send alert to custom webhook URL (generic JSON POST)."""
    payload = {
        "level": level,
        "title": title,
        "message": message,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": "insight",
    }
    return await _post(url, payload)


async def _post(url: str, payload: dict) -> bool:
    """HTTP POST to webhook URL."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code < 300:
                logger.info(f"Webhook sent: {url[:50]}... -> {resp.status_code}")
                return True
            else:
                logger.warning(f"Webhook failed: {url[:50]}... -> {resp.status_code}")
                return False
    except Exception as e:
        logger.error(f"Webhook error: {url[:50]}... -> {e}")
        return False


async def send_to_all_webhooks(webhooks: list[dict], level: str, title: str, message: str, source: str = ""):
    """Send alert to all enabled webhooks."""
    for wh in webhooks:
        if not wh.get("enabled", True):
            continue
        url = wh.get("url", "")
        wh_type = wh.get("type", "custom")
        # Check if webhook subscribes to this event level
        events = wh.get("events", ["critical", "error"])
        if level not in events:
            continue
        try:
            if wh_type == "slack":
                await send_slack(url, level, title, message, source)
            elif wh_type == "discord":
                await send_discord(url, level, title, message, source)
            else:
                await send_custom(url, level, title, message, source)
        except Exception as e:
            logger.error(f"Webhook send failed ({wh.get('name', 'unknown')}): {e}")
