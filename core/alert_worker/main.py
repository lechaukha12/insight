"""
Insight Alert Worker — Background processing service.
Runs as a standalone process (no HTTP server).

Tasks:
1. Alert Evaluation — Check metrics vs notification rules every 60s
2. Agent Health — Mark agents offline if heartbeat > 90s
3. Retention Cleanup — Apply TTL policies daily at 03:00
4. Daily Report — Generate + send report via Telegram at 08:00
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database.db import (
    init_db, list_agents, get_latest_metrics_per_agent,
    get_events, get_logs, get_alert_configs, get_rules,
    get_webhooks, update_agent_status, apply_retention_policies,
    save_report,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("insight.worker")

# ─── Config ───
ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))
AGENT_HEALTH_INTERVAL = int(os.getenv("AGENT_HEALTH_INTERVAL", "60"))
AGENT_OFFLINE_SECONDS = int(os.getenv("AGENT_OFFLINE_SECONDS", "90"))
REPORT_HOUR = int(os.getenv("REPORT_HOUR", "8"))       # 8:00 AM
RETENTION_HOUR = int(os.getenv("RETENTION_HOUR", "3"))  # 3:00 AM
REPORT_TIMEZONE = os.getenv("REPORT_TIMEZONE", "Asia/Ho_Chi_Minh")


# ════════════════════════════════════════════════
# ALERT EVALUATION
# ════════════════════════════════════════════════

async def check_alerts():
    """Evaluate metrics against notification rules and send alerts."""
    try:
        rules = get_rules(enabled_only=True)
        if not rules:
            return

        metrics_map = get_latest_metrics_per_agent()
        configs = get_alert_configs()
        webhooks = get_webhooks(enabled_only=True)

        for agent_id, metrics in metrics_map.items():
            for m in metrics:
                name = m.get("metric_name", "")
                value = m.get("metric_value", 0)
                for rule in rules:
                    if rule["metric_name"] != name:
                        continue
                    op, threshold = rule["operator"], rule["threshold"]
                    triggered = (
                        (op == ">" and value > threshold) or
                        (op == ">=" and value >= threshold) or
                        (op == "<" and value < threshold) or
                        (op == "<=" and value <= threshold) or
                        (op == "==" and value == threshold)
                    )
                    if triggered:
                        msg = f"Agent {agent_id}: {name} = {value:.1f} ({op} {threshold})"
                        await _send_alert("warning", f"Rule: {rule['name']}", msg, f"rule:{rule['id']}", configs, webhooks)

    except Exception as e:
        logger.error(f"Alert check failed: {e}")


# ════════════════════════════════════════════════
# AGENT HEALTH CHECK
# ════════════════════════════════════════════════

async def check_agent_health():
    """Mark agents as offline if heartbeat is stale."""
    try:
        agents = list_agents()
        now = datetime.now(timezone.utc)
        for agent in agents:
            if agent.get("status") != "active":
                continue
            last_hb = agent.get("last_heartbeat")
            if isinstance(last_hb, str):
                try:
                    last_hb = datetime.strptime(last_hb, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    continue
            if last_hb and hasattr(last_hb, 'replace'):
                if last_hb.tzinfo is None:
                    last_hb = last_hb.replace(tzinfo=timezone.utc)
                elapsed = (now - last_hb).total_seconds()
                if elapsed > AGENT_OFFLINE_SECONDS:
                    update_agent_status(agent["id"], "offline")
                    logger.info(f"Agent {agent.get('hostname', agent['id'])} marked offline (heartbeat {elapsed:.0f}s ago)")
    except Exception as e:
        logger.error(f"Agent health check failed: {e}")


# ════════════════════════════════════════════════
# DAILY REPORT
# ════════════════════════════════════════════════

async def generate_daily_report():
    """Generate and send daily monitoring report."""
    try:
        from report_service.reports import generate_report, format_report_telegram

        agents = list_agents()
        metrics_map = get_latest_metrics_per_agent()
        events = get_events(last_hours=24, limit=200)
        logs = get_logs(last_hours=24, limit=200)

        report = generate_report(agents, metrics_map, events, logs, report_type="daily")
        save_report("daily", report, sent_to=[])

        # Send via Telegram if configured
        configs = get_alert_configs()
        telegram_configs = [c for c in configs if c.get("channel") == "telegram" and c.get("enabled")]
        if telegram_configs:
            from alert_service.providers import TelegramProvider
            text = format_report_telegram(report)
            for cfg in telegram_configs:
                config = cfg.get("config", {})
                bot_token = config.get("bot_token", os.getenv("TELEGRAM_BOT_TOKEN", ""))
                chat_id = config.get("chat_id", os.getenv("TELEGRAM_CHAT_ID", ""))
                if bot_token and chat_id:
                    provider = TelegramProvider(bot_token, chat_id)
                    await provider.send(text)
                    logger.info("Daily report sent via Telegram")

        logger.info(f"Daily report generated: {report.get('summary', {})}")

    except Exception as e:
        logger.error(f"Daily report failed: {e}")


# ════════════════════════════════════════════════
# RETENTION CLEANUP
# ════════════════════════════════════════════════

async def apply_retention():
    """Apply data retention policies to clean up old data."""
    try:
        result = apply_retention_policies()
        logger.info(f"Retention applied: {result}")
    except Exception as e:
        logger.error(f"Retention cleanup failed: {e}")


# ════════════════════════════════════════════════
# ALERT DISPATCH (shared helper)
# ════════════════════════════════════════════════

_recent_alerts: dict[str, float] = {}
DEDUP_SECONDS = int(os.getenv("ALERT_DEDUP_SECONDS", "300"))


async def _send_alert(level: str, title: str, message: str, source: str,
                      configs: list[dict], webhooks: list[dict]):
    """Send alert to all configured channels with deduplication."""
    # Dedup
    key = f"{title}|{source}"
    now = time.time()
    if key in _recent_alerts and now - _recent_alerts[key] < DEDUP_SECONDS:
        return
    _recent_alerts[key] = now
    # Cleanup
    cutoff = now - DEDUP_SECONDS
    for k in list(_recent_alerts):
        if _recent_alerts[k] < cutoff:
            del _recent_alerts[k]

    # Alert providers (Telegram, Email)
    try:
        from alert_service.providers import alert_manager
        await alert_manager.send_alert(level=level, title=title, message=message,
                                       source=source, configs=configs)
    except Exception as e:
        logger.error(f"Alert provider failed: {e}")

    # Webhooks (Slack, Discord, custom)
    try:
        from api_gateway.webhook_sender import send_to_all_webhooks
        await send_to_all_webhooks(webhooks, level, title, message, source)
    except Exception as e:
        logger.error(f"Webhook dispatch failed: {e}")


# ════════════════════════════════════════════════
# SCHEDULER MAIN LOOP
# ════════════════════════════════════════════════

async def scheduler():
    """Main scheduler loop with configurable intervals."""
    logger.info("Insight Alert Worker v1.0.0 starting...")
    init_db()
    logger.info("Database initialized")

    last_alert_check = 0
    last_health_check = 0
    last_report_hour = -1
    last_retention_hour = -1

    while True:
        try:
            now = time.time()

            # Alert evaluation (every ALERT_CHECK_INTERVAL seconds)
            if now - last_alert_check >= ALERT_CHECK_INTERVAL:
                await check_alerts()
                last_alert_check = now

            # Agent health check (every AGENT_HEALTH_INTERVAL seconds)
            if now - last_health_check >= AGENT_HEALTH_INTERVAL:
                await check_agent_health()
                last_health_check = now

            # Daily report (at REPORT_HOUR)
            try:
                import zoneinfo
                local_tz = zoneinfo.ZoneInfo(REPORT_TIMEZONE)
            except Exception:
                local_tz = timezone.utc
            local_now = datetime.now(local_tz)
            current_hour = local_now.hour

            if current_hour == REPORT_HOUR and last_report_hour != current_hour:
                await generate_daily_report()
                last_report_hour = current_hour
            elif current_hour != REPORT_HOUR:
                last_report_hour = -1

            # Retention cleanup (at RETENTION_HOUR)
            if current_hour == RETENTION_HOUR and last_retention_hour != current_hour:
                await apply_retention()
                last_retention_hour = current_hour
            elif current_hour != RETENTION_HOUR:
                last_retention_hour = -1

        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(scheduler())
