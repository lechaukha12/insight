"""
Insight Windows Agent - System Resource Monitoring Agent

Monitors Windows server resources and sends data to Insight Core API:
- CPU usage (total + per-core)
- Memory usage (total, used, available)
- Disk usage (per drive)
- Network I/O
- Uptime
- Process count
- Windows event log errors

Uses psutil (cross-platform) for metric collection.
Can optionally use WMI for Windows-specific metrics.
"""

import logging
import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone

import requests

# ─── Configuration ───

CORE_API_URL = os.getenv("INSIGHT_CORE_URL", "http://localhost:8080")
API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")
AGENT_ID = os.getenv("AGENT_ID", f"win-agent-{socket.gethostname()}")
AGENT_NAME = os.getenv("AGENT_NAME", f"Windows Agent ({socket.gethostname()})")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
DAILY_SCAN_HOUR = int(os.getenv("DAILY_SCAN_HOUR", "0"))
DAILY_SCAN_MINUTE = int(os.getenv("DAILY_SCAN_MINUTE", "45"))

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", "90"))
MEMORY_THRESHOLD = float(os.getenv("MEMORY_THRESHOLD", "90"))
DISK_THRESHOLD = float(os.getenv("DISK_THRESHOLD", "95"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("insight.windows-agent")

try:
    import psutil
except ImportError:
    logger.error("psutil not installed. Install with: pip install psutil")
    sys.exit(1)

# Optional WMI support for Windows event logs
wmi_available = False
if platform.system() == "Windows":
    try:
        import wmi as wmi_module
        wmi_available = True
    except ImportError:
        logger.warning("wmi package not available - Windows event log collection disabled")


# ─── Core API Communication ───


def send_to_core(endpoint: str, data: dict) -> bool:
    url = f"{CORE_API_URL}{endpoint}"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        if resp.status_code < 300:
            logger.info(f"Sent to {endpoint}: {resp.json()}")
            return True
        else:
            logger.error(f"Failed to send to {endpoint}: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Connection to core failed: {e}")
        return False


def send_heartbeat():
    send_to_core(f"/api/v1/agents/{AGENT_ID}/heartbeat", {})


# ─── Metric Collection ───


def collect_all_metrics() -> list[dict]:
    """Collect all system metrics."""
    metrics = []
    hostname = socket.gethostname()
    labels = {"host": hostname}

    # CPU
    cpu_percent = psutil.cpu_percent(interval=1)
    metrics.append({"metric_name": "cpu_percent", "metric_value": cpu_percent, "labels": labels})
    metrics.append({"metric_name": "cpu_count", "metric_value": float(psutil.cpu_count()), "labels": labels})

    per_core = psutil.cpu_percent(interval=0.5, percpu=True)
    for i, pct in enumerate(per_core):
        metrics.append({"metric_name": "cpu_core_percent", "metric_value": pct, "labels": {**labels, "core": str(i)}})

    # Memory
    mem = psutil.virtual_memory()
    metrics.extend([
        {"metric_name": "memory_total_bytes", "metric_value": float(mem.total), "labels": labels},
        {"metric_name": "memory_used_bytes", "metric_value": float(mem.used), "labels": labels},
        {"metric_name": "memory_available_bytes", "metric_value": float(mem.available), "labels": labels},
        {"metric_name": "memory_percent", "metric_value": mem.percent, "labels": labels},
    ])

    # Disk - all partitions
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disk_labels = {**labels, "mountpoint": part.mountpoint, "device": part.device, "fstype": part.fstype}
            metrics.extend([
                {"metric_name": "disk_total_bytes", "metric_value": float(usage.total), "labels": disk_labels},
                {"metric_name": "disk_used_bytes", "metric_value": float(usage.used), "labels": disk_labels},
                {"metric_name": "disk_percent", "metric_value": usage.percent, "labels": disk_labels},
            ])
        except (PermissionError, OSError):
            continue

    # Network
    try:
        net_io = psutil.net_io_counters()
        metrics.extend([
            {"metric_name": "network_bytes_sent", "metric_value": float(net_io.bytes_sent), "labels": labels},
            {"metric_name": "network_bytes_recv", "metric_value": float(net_io.bytes_recv), "labels": labels},
        ])
    except Exception:
        pass

    # Uptime & Processes
    uptime = time.time() - psutil.boot_time()
    metrics.append({"metric_name": "uptime_seconds", "metric_value": uptime, "labels": {**labels, "os": "Windows", "version": platform.version()}})
    metrics.append({"metric_name": "process_count", "metric_value": float(len(psutil.pids())), "labels": labels})

    return metrics


def collect_windows_events() -> list[dict]:
    """Collect recent Windows Event Log errors (requires wmi)."""
    events = []
    if not wmi_available:
        return events

    try:
        c = wmi_module.WMI()
        # Query recent error events from System and Application logs
        for log_source in ["System", "Application"]:
            try:
                wql = (
                    f"SELECT * FROM Win32_NTLogEvent "
                    f"WHERE Logfile='{log_source}' AND EventType=1 "
                    f"AND TimeWritten > '{(datetime.now() - __import__('datetime').timedelta(hours=1)).strftime('%Y%m%d%H%M%S')}.000000+000'"
                )
                for event in c.query(wql)[:20]:
                    events.append({
                        "level": "error",
                        "title": f"Windows Event: {event.SourceName}",
                        "message": (event.Message or "")[:500],
                        "source": f"windows/{socket.gethostname()}",
                        "details": {
                            "event_id": event.EventCode,
                            "log": log_source,
                            "source_name": event.SourceName,
                        },
                    })
            except Exception as e:
                logger.debug(f"Failed to query {log_source} events: {e}")
    except Exception as e:
        logger.error(f"WMI query failed: {e}")

    return events


def check_thresholds(metrics: list[dict]) -> list[dict]:
    """Check metrics against thresholds."""
    events = []
    hostname = socket.gethostname()

    for m in metrics:
        name = m.get("metric_name", "")
        value = m.get("metric_value", 0)
        labels = m.get("labels", {})

        if name == "cpu_percent" and value > CPU_THRESHOLD:
            events.append({
                "level": "critical" if value > CPU_THRESHOLD + 5 else "error",
                "title": f"CPU usage cao: {value:.1f}%",
                "message": f"Server {hostname}: CPU = {value:.1f}% (ngưỡng: {CPU_THRESHOLD}%)",
                "source": f"windows/{hostname}",
                "resource": hostname,
            })
        elif name == "memory_percent" and value > MEMORY_THRESHOLD:
            events.append({
                "level": "critical" if value > MEMORY_THRESHOLD + 5 else "error",
                "title": f"Memory usage cao: {value:.1f}%",
                "message": f"Server {hostname}: RAM = {value:.1f}% (ngưỡng: {MEMORY_THRESHOLD}%)",
                "source": f"windows/{hostname}",
                "resource": hostname,
            })
        elif name == "disk_percent" and value > DISK_THRESHOLD:
            mp = labels.get("mountpoint", "")
            events.append({
                "level": "critical" if value > DISK_THRESHOLD + 2 else "error",
                "title": f"Disk usage cao: {mp} = {value:.1f}%",
                "message": f"Server {hostname}: Disk {mp} = {value:.1f}% (ngưỡng: {DISK_THRESHOLD}%)",
                "source": f"windows/{hostname}",
                "resource": hostname,
            })

    return events


# ─── Main Loop ───


def run_scan():
    logger.info("Starting scan...")
    metrics = collect_all_metrics()
    events = check_thresholds(metrics)
    win_events = collect_windows_events()
    all_events = events + win_events

    if metrics:
        send_to_core("/api/v1/metrics", {
            "agent_id": AGENT_ID, "agent_name": AGENT_NAME,
            "agent_type": "windows", "hostname": socket.gethostname(),
            "metrics": metrics,
        })

    if all_events:
        send_to_core("/api/v1/events", {
            "agent_id": AGENT_ID, "agent_name": AGENT_NAME,
            "agent_type": "windows", "hostname": socket.gethostname(),
            "events": all_events,
        })

    send_heartbeat()
    logger.info(f"Scan complete: {len(metrics)} metrics, {len(all_events)} events")


def main():
    logger.info(f"Insight Windows Agent starting...")
    logger.info(f"   Agent ID: {AGENT_ID}")
    logger.info(f"   Hostname: {socket.gethostname()}")
    logger.info(f"   OS: {platform.system()} {platform.version()}")
    logger.info(f"   Core URL: {CORE_API_URL}")
    logger.info(f"   Scan Interval: {SCAN_INTERVAL}s")

    daily_done_today = False
    last_scan_day = None

    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()
            if last_scan_day != today:
                daily_done_today = False
                last_scan_day = today

            if now.hour == DAILY_SCAN_HOUR and now.minute == DAILY_SCAN_MINUTE and not daily_done_today:
                logger.info("Running daily comprehensive scan...")
                run_scan()
                send_to_core("/api/v1/reports/generate", {"report_type": "daily", "channels": ["telegram"]})
                daily_done_today = True
            else:
                run_scan()
        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
