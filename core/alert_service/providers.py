"""
Insight Alert Service - Multi-channel notification providers.
Supports Telegram, Email, and Webhook.
"""

import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger("insight.alert")


class TelegramProvider:
    """Send alerts via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send(self, message: str, parse_mode: str = "HTML") -> bool:
        # Split long messages (Telegram limit: 4096 chars)
        chunks = self._split_message(message, 4096)
        success = True
        async with httpx.AsyncClient(timeout=30) as client:
            for chunk in chunks:
                try:
                    resp = await client.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": self.chat_id,
                            "text": chunk,
                            "parse_mode": parse_mode,
                            "disable_web_page_preview": True,
                        },
                    )
                    if resp.status_code != 200:
                        logger.error(f"Telegram error: {resp.status_code} - {resp.text}")
                        success = False
                except Exception as e:
                    logger.error(f"Telegram send failed: {e}")
                    success = False
        return success

    def _split_message(self, text: str, max_len: int) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks


class EmailProvider:
    """Send alerts via SMTP email."""

    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str,
                 from_addr: str, to_addrs: list[str], use_tls: bool = True):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    async def send(self, subject: str, body: str, html: bool = True) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))

            if self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)

            server.login(self.username, self.password)
            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            server.quit()
            logger.info(f"Email sent to {self.to_addrs}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False


class WebhookProvider:
    """Send alerts via HTTP webhook."""

    def __init__(self, url: str, headers: dict[str, str] = None, method: str = "POST"):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}
        self.method = method

    async def send(self, payload: dict[str, Any]) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    method=self.method,
                    url=self.url,
                    headers=self.headers,
                    json=payload,
                )
                if resp.status_code < 300:
                    logger.info(f"Webhook sent to {self.url}")
                    return True
                else:
                    logger.error(f"Webhook error: {resp.status_code} - {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return False


class AlertManager:
    """
    Central alert manager.
    Loads alert configs from DB and dispatches alerts to the appropriate channels.
    Implements deduplication to avoid alert storms.
    """

    def __init__(self):
        self._recent_alerts: dict[str, float] = {}  # hash -> timestamp
        self.dedup_seconds = int(os.getenv("ALERT_DEDUP_SECONDS", "300"))

    def _make_key(self, title: str, source: str) -> str:
        return f"{title}|{source}"

    def _is_duplicate(self, title: str, source: str) -> bool:
        import time
        key = self._make_key(title, source)
        now = time.time()
        if key in self._recent_alerts:
            if now - self._recent_alerts[key] < self.dedup_seconds:
                return True
        self._recent_alerts[key] = now
        # Cleanup old entries
        cutoff = now - self.dedup_seconds
        self._recent_alerts = {k: v for k, v in self._recent_alerts.items() if v > cutoff}
        return False

    async def send_alert(self, level: str, title: str, message: str,
                         source: str = "", configs: list[dict] = None) -> list[str]:
        """
        Send alert to all configured channels.
        Returns list of channels that were successfully notified.
        """
        if self._is_duplicate(title, source):
            logger.info(f"Alert deduplicated: {title}")
            return []

        if configs is None:
            from core.shared.database.db import get_alert_configs
            configs = get_alert_configs()

        sent_to = []
        for cfg in configs:
            if not cfg.get("enabled", True):
                continue

            alert_levels = cfg.get("alert_levels", ["critical", "error"])
            if level not in alert_levels:
                continue

            channel = cfg["channel"]
            channel_config = cfg.get("config", {})

            try:
                if channel == "telegram":
                    provider = TelegramProvider(
                        bot_token=channel_config.get("bot_token", ""),
                        chat_id=channel_config.get("chat_id", ""),
                    )
                    text = self._format_telegram(level, title, message)
                    if await provider.send(text):
                        sent_to.append("telegram")

                elif channel == "email":
                    provider = EmailProvider(
                        smtp_host=channel_config.get("smtp_host", ""),
                        smtp_port=channel_config.get("smtp_port", 587),
                        username=channel_config.get("username", ""),
                        password=channel_config.get("password", ""),
                        from_addr=channel_config.get("from_addr", ""),
                        to_addrs=channel_config.get("to_addrs", []),
                        use_tls=channel_config.get("use_tls", True),
                    )
                    subject = f"[Insight Alert - {level.upper()}] {title}"
                    body = self._format_email(level, title, message)
                    if await provider.send(subject, body):
                        sent_to.append("email")

                elif channel == "webhook":
                    provider = WebhookProvider(
                        url=channel_config.get("url", ""),
                        headers=channel_config.get("headers", {}),
                    )
                    payload = {
                        "level": level,
                        "title": title,
                        "message": message,
                        "source": source,
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                    }
                    if await provider.send(payload):
                        sent_to.append("webhook")

            except Exception as e:
                logger.error(f"Alert channel {channel} error: {e}")

        return sent_to

    def _format_telegram(self, level: str, title: str, message: str) -> str:
        level_icon = {"critical": "🔴", "error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(level, "📋")
        return (
            f"{level_icon} <b>[{level.upper()}] {title}</b>\n\n"
            f"{message}\n\n"
            f"🕐 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def _format_email(self, level: str, title: str, message: str) -> str:
        color = {"critical": "#dc3545", "error": "#fd7e14", "warning": "#ffc107", "info": "#0d6efd"}.get(level, "#6c757d")
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: {color}; color: white; padding: 16px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0;">[{level.upper()}] {title}</h2>
            </div>
            <div style="padding: 16px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px;">
                <pre style="white-space: pre-wrap; font-size: 14px;">{message}</pre>
                <hr/>
                <p style="color: #666; font-size: 12px;">Insight Monitoring System</p>
            </div>
        </div>
        """


# Singleton
alert_manager = AlertManager()
