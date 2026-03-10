"""
Insight Monitoring System - Pydantic Schemas
Defines all data models for API requests/responses and database records.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ─── Enums ───


class AgentType(str, Enum):
    KUBERNETES = "kubernetes"
    LINUX = "linux"
    WINDOWS = "windows"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class AlertLevel(str, Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AlertChannel(str, Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"


class ReportType(str, Enum):
    DAILY = "daily"
    ON_DEMAND = "on_demand"


# ─── Agent Models ───


class AgentRegistration(BaseModel):
    name: str
    agent_type: AgentType
    hostname: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class AgentInfo(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    agent_type: AgentType
    hostname: str = ""
    status: AgentStatus = AgentStatus.ACTIVE
    labels: dict[str, str] = Field(default_factory=dict)
    last_heartbeat: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)


# ─── Metrics Models ───


class MetricData(BaseModel):
    metric_name: str
    metric_value: float
    labels: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class MetricsPayload(BaseModel):
    agent_id: str
    agent_type: AgentType
    cluster_name: str = ""
    hostname: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    metrics: list[MetricData] = Field(default_factory=list)


# ─── Event / Alert Models ───


class AlertEvent(BaseModel):
    level: AlertLevel
    title: str
    message: str
    source: str = ""
    namespace: str = ""
    resource: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class EventsPayload(BaseModel):
    agent_id: str
    agent_type: AgentType
    cluster_name: str = ""
    hostname: str = ""
    events: list[AlertEvent] = Field(default_factory=list)


# ─── Log Models ───


class LogEntry(BaseModel):
    namespace: str = ""
    pod_name: str = ""
    container: str = ""
    log_level: str = "error"
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class LogsPayload(BaseModel):
    agent_id: str
    agent_type: AgentType
    cluster_name: str = ""
    hostname: str = ""
    logs: list[LogEntry] = Field(default_factory=list)


# ─── Alert Config Models ───


class TelegramConfig(BaseModel):
    bot_token: str
    chat_id: str
    enabled: bool = True


class EmailConfig(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    username: str
    password: str
    from_addr: str
    to_addrs: list[str]
    use_tls: bool = True
    enabled: bool = True


class WebhookConfig(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    method: str = "POST"
    enabled: bool = True


class AlertConfigCreate(BaseModel):
    channel: AlertChannel
    config: dict[str, Any]
    enabled: bool = True
    alert_levels: list[AlertLevel] = Field(
        default_factory=lambda: [AlertLevel.CRITICAL, AlertLevel.ERROR]
    )


class AlertConfigResponse(AlertConfigCreate):
    id: UUID
    created_at: datetime


# ─── Report Models ───


class ReportRequest(BaseModel):
    report_type: ReportType = ReportType.ON_DEMAND
    channels: list[AlertChannel] = Field(
        default_factory=lambda: [AlertChannel.TELEGRAM]
    )
    include_metrics: bool = True
    include_events: bool = True
    include_logs: bool = True


class ReportResponse(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    report_type: ReportType
    content: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.now)
    sent_to: list[str] = Field(default_factory=list)


# ─── Dashboard Query Models ───


class DashboardSummary(BaseModel):
    total_agents: int = 0
    active_agents: int = 0
    total_alerts_today: int = 0
    critical_alerts: int = 0
    agents: list[AgentInfo] = Field(default_factory=list)


class TimeRange(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    last_hours: int = 24


# ─── Settings Models ───


class AutoReportSetting(BaseModel):
    enabled: bool = False
    schedule: str = "45 0 * * *"  # 7:45 AM UTC+7
    channels: list[AlertChannel] = Field(
        default_factory=lambda: [AlertChannel.TELEGRAM]
    )
    timezone: str = "Asia/Ho_Chi_Minh"


class SystemSettings(BaseModel):
    auto_report: AutoReportSetting = Field(default_factory=AutoReportSetting)
    alert_dedup_minutes: int = 5
    metric_retention_days: int = 30
