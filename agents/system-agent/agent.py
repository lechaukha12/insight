"""
Insight System Agent v5.0.3 — Unified System Resource Monitoring

Auto-detects OS (Linux/Windows/macOS) and monitors:
- CPU usage (total + per-core + load average on Unix)
- Memory usage (total, used, available, swap)
- Disk usage (per mount/drive)
- Network I/O
- Uptime / Process count
- Process list with CPU/RAM per process (top 30)
- System log collection:
  - Linux: journald / syslog files
  - Windows: Windows Event Log (WMI / PowerShell)
  - macOS: /var/log/system.log

Supports two modes:
1. Real-time monitoring (every SCAN_INTERVAL seconds)
2. Daily comprehensive scan for report generation
"""

import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ─── Configuration ───

CORE_API_URL = os.getenv("INSIGHT_CORE_URL", "http://localhost:8080")
API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")  # New token-based auth

OS_TYPE = platform.system().lower()  # 'linux', 'windows', 'darwin'
HOSTNAME = socket.gethostname()
AGENT_VERSION = "5.0.3"
OS_INFO = f"{platform.system()} {platform.release()}"

AGENT_ID = os.getenv("AGENT_ID", f"system-agent-{HOSTNAME}")
AGENT_NAME = os.getenv("AGENT_NAME", f"System Agent ({HOSTNAME})")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
DAILY_SCAN_HOUR = int(os.getenv("DAILY_SCAN_HOUR", "0"))
DAILY_SCAN_MINUTE = int(os.getenv("DAILY_SCAN_MINUTE", "45"))

# Thresholds for alerts
CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", "90"))
MEMORY_THRESHOLD = float(os.getenv("MEMORY_THRESHOLD", "90"))
DISK_THRESHOLD = float(os.getenv("DISK_THRESHOLD", "95"))

# Log collection config (Linux only)
LOG_FILES = os.getenv("LOG_FILES", "/var/log/syslog,/var/log/messages,/var/log/auth.log").split(",")
LOG_LINES = int(os.getenv("LOG_LINES", "50"))
USE_JOURNALD = os.getenv("USE_JOURNALD", "auto")  # auto, true, false

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("insight.system-agent")

# Import psutil
try:
    import psutil
except ImportError:
    logger.error("psutil not installed. Install with: pip install psutil")
    sys.exit(1)

# Optional Windows-specific imports
wmi_available = False
if OS_TYPE == "windows":
    try:
        import wmi as wmi_module
        wmi_available = True
    except ImportError:
        logger.warning("wmi package not available - using PowerShell for event logs")


# ═══════════════════════════════════════════════════════════
# Core API Communication
# ═══════════════════════════════════════════════════════════

def send_to_core(endpoint: str, data: dict) -> bool:
    url = f"{CORE_API_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if AGENT_TOKEN:
        headers["X-Agent-Token"] = AGENT_TOKEN
    else:
        headers["X-API-Key"] = API_KEY
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        if resp.status_code < 300:
            logger.info(f"Sent to {endpoint}: {resp.json()}")
            return True
        else:
            logger.error(f"Failed to send to {endpoint}: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Connection to core failed: {e}")
        return False


def connect_to_core():
    """Register agent with core via POST /agents/connect (token-based auto-registration)."""
    global AGENT_ID
    if not AGENT_TOKEN:
        logger.info("No AGENT_TOKEN set, using legacy API key auth")
        return
    url = f"{CORE_API_URL}/api/v1/agents/connect"
    headers = {"Content-Type": "application/json", "X-Agent-Token": AGENT_TOKEN}
    data = {
        "agent_id": AGENT_ID,
        "name": AGENT_NAME,
        "agent_type": "system",
        "hostname": HOSTNAME,
        "version": AGENT_VERSION,
        "os_info": OS_INFO,
        "labels": {"os": OS_TYPE, "platform": platform.machine()},
    }
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        if resp.status_code < 300:
            result = resp.json()
            AGENT_ID = result.get("agent_id", AGENT_ID)
            logger.info(f"Connected to core: agent_id={AGENT_ID}")
        else:
            logger.error(f"Connect failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Connect to core failed: {e}")


def send_heartbeat():
    send_to_core(f"/api/v1/agents/{AGENT_ID}/heartbeat", {})


# ═══════════════════════════════════════════════════════════
# System Metrics Collection (Cross-Platform via psutil)
# ═══════════════════════════════════════════════════════════

def collect_cpu_metrics() -> list[dict]:
    """Collect CPU usage metrics (cross-platform)."""
    metrics = []
    labels = {"host": HOSTNAME, "os": OS_TYPE}

    # Overall CPU percent
    cpu_percent = psutil.cpu_percent(interval=1)
    metrics.append({"metric_name": "cpu_percent", "metric_value": cpu_percent, "labels": labels})

    # Per-core usage
    per_core = psutil.cpu_percent(interval=0.5, percpu=True)
    for i, core_pct in enumerate(per_core):
        metrics.append({"metric_name": "cpu_core_percent", "metric_value": core_pct, "labels": {**labels, "core": str(i)}})

    # CPU count
    metrics.append({"metric_name": "cpu_count", "metric_value": float(psutil.cpu_count()), "labels": labels})

    # Load average (Unix only — Linux/macOS)
    try:
        load1, load5, load15 = os.getloadavg()
        metrics.extend([
            {"metric_name": "load_avg_1m", "metric_value": load1, "labels": labels},
            {"metric_name": "load_avg_5m", "metric_value": load5, "labels": labels},
            {"metric_name": "load_avg_15m", "metric_value": load15, "labels": labels},
        ])
    except (OSError, AttributeError):
        pass  # Not available on Windows

    return metrics


def collect_memory_metrics() -> list[dict]:
    """Collect memory usage metrics (cross-platform)."""
    metrics = []
    labels = {"host": HOSTNAME, "os": OS_TYPE}

    mem = psutil.virtual_memory()
    metrics.extend([
        {"metric_name": "memory_total_bytes", "metric_value": float(mem.total), "labels": labels},
        {"metric_name": "memory_used_bytes", "metric_value": float(mem.used), "labels": labels},
        {"metric_name": "memory_available_bytes", "metric_value": float(mem.available), "labels": labels},
        {"metric_name": "memory_percent", "metric_value": mem.percent, "labels": labels},
    ])

    # Swap
    swap = psutil.swap_memory()
    metrics.extend([
        {"metric_name": "swap_total_bytes", "metric_value": float(swap.total), "labels": labels},
        {"metric_name": "swap_used_bytes", "metric_value": float(swap.used), "labels": labels},
        {"metric_name": "swap_percent", "metric_value": swap.percent, "labels": labels},
    ])

    return metrics


def collect_disk_metrics() -> list[dict]:
    """Collect disk usage metrics for all mount points/drives (cross-platform)."""
    metrics = []

    # Skip virtual/special filesystems
    skip_fstypes = {"squashfs", "tmpfs", "devtmpfs", "overlay", "devfs", "autofs"}

    for partition in psutil.disk_partitions():
        if partition.fstype in skip_fstypes:
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            labels = {
                "host": HOSTNAME, "os": OS_TYPE,
                "mountpoint": partition.mountpoint,
                "device": partition.device,
                "fstype": partition.fstype,
            }
            metrics.extend([
                {"metric_name": "disk_total_bytes", "metric_value": float(usage.total), "labels": labels},
                {"metric_name": "disk_used_bytes", "metric_value": float(usage.used), "labels": labels},
                {"metric_name": "disk_free_bytes", "metric_value": float(usage.free), "labels": labels},
                {"metric_name": "disk_percent", "metric_value": usage.percent, "labels": labels},
            ])
        except (PermissionError, OSError):
            continue

    # Disk I/O
    try:
        disk_io = psutil.disk_io_counters()
        if disk_io:
            labels = {"host": HOSTNAME, "os": OS_TYPE}
            metrics.extend([
                {"metric_name": "disk_read_bytes_total", "metric_value": float(disk_io.read_bytes), "labels": labels},
                {"metric_name": "disk_write_bytes_total", "metric_value": float(disk_io.write_bytes), "labels": labels},
            ])
    except Exception:
        pass

    return metrics


def collect_network_metrics() -> list[dict]:
    """Collect network I/O metrics (cross-platform)."""
    metrics = []
    labels = {"host": HOSTNAME, "os": OS_TYPE}

    try:
        net_io = psutil.net_io_counters()
        metrics.extend([
            {"metric_name": "network_bytes_sent", "metric_value": float(net_io.bytes_sent), "labels": labels},
            {"metric_name": "network_bytes_recv", "metric_value": float(net_io.bytes_recv), "labels": labels},
            {"metric_name": "network_packets_sent", "metric_value": float(net_io.packets_sent), "labels": labels},
            {"metric_name": "network_packets_recv", "metric_value": float(net_io.packets_recv), "labels": labels},
            {"metric_name": "network_errors_in", "metric_value": float(net_io.errin), "labels": labels},
            {"metric_name": "network_errors_out", "metric_value": float(net_io.errout), "labels": labels},
        ])
    except Exception:
        pass

    return metrics


def collect_system_info() -> list[dict]:
    """Collect general system info metrics (cross-platform)."""
    metrics = []
    labels = {"host": HOSTNAME, "os": OS_TYPE, "release": platform.release(), "version": platform.version()}

    # Uptime
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    metrics.append({"metric_name": "uptime_seconds", "metric_value": uptime_seconds, "labels": labels})

    # Process count
    metrics.append({"metric_name": "process_count", "metric_value": float(len(psutil.pids())), "labels": {"host": HOSTNAME, "os": OS_TYPE}})

    return metrics


# ═══════════════════════════════════════════════════════════
# Process List (Cross-Platform)
# ═══════════════════════════════════════════════════════════

def collect_process_list() -> list[dict]:
    """Collect top 30 processes sorted by CPU usage (cross-platform)."""
    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent',
                                          'memory_info', 'status', 'cmdline', 'create_time']):
            try:
                info = proc.info
                username = info["username"] or "system"
                # Windows: Remove domain prefix (DOMAIN\user -> user)
                if OS_TYPE == "windows" and "\\" in username:
                    username = username.split("\\")[-1]

                processes.append({
                    "pid": info["pid"],
                    "name": info["name"] or "unknown",
                    "username": username,
                    "cpu_percent": info["cpu_percent"] or 0.0,
                    "memory_percent": round(info["memory_percent"] or 0.0, 1),
                    "memory_mb": round((info["memory_info"].rss / 1048576) if info["memory_info"] else 0, 1),
                    "status": info["status"] or "unknown",
                    "command": " ".join(info["cmdline"][:5]) if info["cmdline"] else info["name"],
                    "created": datetime.fromtimestamp(info["create_time"], tz=timezone.utc).isoformat() if info["create_time"] else None,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"Process collection error: {e}")

    processes.sort(key=lambda x: x["cpu_percent"], reverse=True)
    return processes[:30]


# ═══════════════════════════════════════════════════════════
# System Log Collection (OS-Specific)
# ═══════════════════════════════════════════════════════════

_last_log_position = {}  # file -> position


# ─── Linux Logs ───

def _has_journald():
    """Check if systemd-journald is available."""
    try:
        result = subprocess.run(["journalctl", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _collect_journald_logs() -> list[dict]:
    """Collect recent system logs from journald (Linux)."""
    logs = []
    try:
        result = subprocess.run(
            ["journalctl", "--since", "5 minutes ago", "-p", "err..emerg",
             "--no-pager", "-o", "json", "-n", str(LOG_LINES)],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    priority = int(entry.get("PRIORITY", 6))
                    level = "critical" if priority <= 2 else "error" if priority <= 3 else "warning" if priority <= 4 else "info"
                    logs.append({
                        "level": level,
                        "source": entry.get("SYSLOG_IDENTIFIER", entry.get("_COMM", "system")),
                        "message": entry.get("MESSAGE", ""),
                        "timestamp": datetime.fromtimestamp(
                            int(entry.get("__REALTIME_TIMESTAMP", 0)) / 1000000, tz=timezone.utc
                        ).isoformat() if entry.get("__REALTIME_TIMESTAMP") else None,
                    })
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception as e:
        logger.debug(f"journalctl failed: {e}")
    return logs


def _collect_file_logs() -> list[dict]:
    """Collect recent error/warning lines from log files (Linux/macOS)."""
    logs = []
    error_keywords = ["error", "fail", "critical", "panic", "fatal", "denied", "refused", "timeout"]

    for log_file in LOG_FILES:
        log_file = log_file.strip()
        if not log_file or not Path(log_file).exists():
            continue

        try:
            last_pos = _last_log_position.get(log_file, 0)
            with open(log_file, "r", errors="ignore") as f:
                f.seek(0, 2)
                file_size = f.tell()

                if last_pos > file_size:
                    last_pos = 0  # File was rotated

                if last_pos == 0:
                    start = max(0, file_size - 8192)
                else:
                    start = last_pos

                f.seek(start)
                lines = f.readlines()
                _last_log_position[log_file] = f.tell()

            for line in lines[-LOG_LINES:]:
                line_lower = line.lower()
                if any(kw in line_lower for kw in error_keywords):
                    level = "critical" if any(w in line_lower for w in ["critical", "panic", "fatal"]) else \
                            "error" if any(w in line_lower for w in ["error", "fail"]) else "warning"
                    logs.append({
                        "level": level,
                        "source": Path(log_file).name,
                        "message": line.strip()[:500],
                    })
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot read {log_file}: {e}")

    return logs


def _collect_linux_logs() -> list[dict]:
    """Collect system logs on Linux (journald or file-based)."""
    use_jd = USE_JOURNALD.lower()
    if use_jd == "true" or (use_jd == "auto" and _has_journald()):
        return _collect_journald_logs()
    return _collect_file_logs()


# ─── Windows Logs ───

def _collect_windows_events() -> list[dict]:
    """Collect recent Windows Event Log errors."""
    events = []

    # Method 1: WMI
    if wmi_available:
        try:
            c = wmi_module.WMI()
            for log_source in ["System", "Application"]:
                try:
                    cutoff = (datetime.now() - timedelta(minutes=5)).strftime("%Y%m%d%H%M%S")
                    wql = (
                        f"SELECT * FROM Win32_NTLogEvent "
                        f"WHERE Logfile='{log_source}' AND EventType<=3 "
                        f"AND TimeWritten > '{cutoff}.000000+000'"
                    )
                    for event in c.query(wql)[:20]:
                        level = "critical" if event.EventType == 1 else "error" if event.EventType == 2 else "warning"
                        events.append({
                            "level": level,
                            "source": f"{log_source}/{event.SourceName}",
                            "message": (event.Message or "")[:500],
                            "details": {"event_id": event.EventCode, "log": log_source, "source_name": event.SourceName},
                        })
                except Exception as e:
                    logger.debug(f"Failed to query {log_source} events: {e}")
        except Exception as e:
            logger.error(f"WMI query failed: {e}")

    # Method 2: PowerShell fallback
    else:
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-EventLog -LogName System -EntryType Error,Warning -Newest 20 | "
                 "Select-Object TimeGenerated,EntryType,Source,Message | ConvertTo-Json"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                entries = json.loads(result.stdout)
                if isinstance(entries, dict):
                    entries = [entries]
                for entry in entries:
                    level = "error" if entry.get("EntryType") == 1 else "warning"
                    events.append({
                        "level": level,
                        "source": f"System/{entry.get('Source', '')}",
                        "message": (entry.get("Message", ""))[:500],
                    })
        except Exception as e:
            logger.debug(f"PowerShell event query failed: {e}")

    return events


# ─── macOS Logs ───

def _collect_macos_logs() -> list[dict]:
    """Collect recent macOS system logs."""
    logs = []
    try:
        result = subprocess.run(
            ["log", "show", "--predicate", "eventType == logEvent AND messageType == error",
             "--last", "5m", "--style", "compact"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n")[-LOG_LINES:]:
                if not line.strip() or line.startswith("Filtering"):
                    continue
                logs.append({"level": "error", "source": "system.log", "message": line.strip()[:500]})
    except Exception as e:
        logger.debug(f"macOS log query failed: {e}")

    # Also try reading /var/log/system.log
    macos_log_files = ["/var/log/system.log"]
    for log_file in macos_log_files:
        if Path(log_file).exists():
            try:
                with open(log_file, "r", errors="ignore") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 8192))
                    for line in f.readlines()[-20:]:
                        if any(kw in line.lower() for kw in ["error", "fail", "critical", "fatal"]):
                            logs.append({"level": "error", "source": "system.log", "message": line.strip()[:500]})
            except (PermissionError, OSError):
                pass

    return logs


# ─── Unified Log Collector ───

def collect_system_logs() -> list[dict]:
    """Collect system logs based on detected OS."""
    if OS_TYPE == "linux":
        return _collect_linux_logs()
    elif OS_TYPE == "windows":
        return _collect_windows_events()
    elif OS_TYPE == "darwin":
        return _collect_macos_logs()
    else:
        logger.warning(f"Unsupported OS for log collection: {OS_TYPE}")
        return _collect_file_logs()  # Fallback to file-based


# ═══════════════════════════════════════════════════════════
# Alert Logic
# ═══════════════════════════════════════════════════════════

def check_thresholds(metrics: list[dict]) -> list[dict]:
    """Check metrics against thresholds and generate alert events."""
    events = []
    os_label = OS_TYPE

    for m in metrics:
        name = m.get("metric_name", "")
        value = m.get("metric_value", 0)
        labels = m.get("labels", {})

        if name == "cpu_percent" and value > CPU_THRESHOLD:
            events.append({
                "level": "critical" if value > CPU_THRESHOLD + 5 else "error",
                "title": f"CPU usage cao: {value:.1f}%",
                "message": f"Server {HOSTNAME}: CPU = {value:.1f}% (ngưỡng: {CPU_THRESHOLD}%)",
                "source": f"{os_label}/{HOSTNAME}",
                "resource": HOSTNAME,
            })

        elif name == "memory_percent" and value > MEMORY_THRESHOLD:
            events.append({
                "level": "critical" if value > MEMORY_THRESHOLD + 5 else "error",
                "title": f"Memory usage cao: {value:.1f}%",
                "message": f"Server {HOSTNAME}: RAM = {value:.1f}% (ngưỡng: {MEMORY_THRESHOLD}%)",
                "source": f"{os_label}/{HOSTNAME}",
                "resource": HOSTNAME,
            })

        elif name == "disk_percent" and value > DISK_THRESHOLD:
            mountpoint = labels.get("mountpoint", "/")
            events.append({
                "level": "critical" if value > DISK_THRESHOLD + 2 else "error",
                "title": f"Disk usage cao: {mountpoint} = {value:.1f}%",
                "message": f"Server {HOSTNAME}: Disk {mountpoint} = {value:.1f}% (ngưỡng: {DISK_THRESHOLD}%)",
                "source": f"{os_label}/{HOSTNAME}",
                "resource": HOSTNAME,
            })

    return events


# ═══════════════════════════════════════════════════════════
# Main Loop
# ═══════════════════════════════════════════════════════════

def run_scan():
    """Run a full metric scan and send to core."""
    logger.info("Starting scan...")

    all_metrics = []
    all_metrics.extend(collect_cpu_metrics())
    all_metrics.extend(collect_memory_metrics())
    all_metrics.extend(collect_disk_metrics())
    all_metrics.extend(collect_network_metrics())
    all_metrics.extend(collect_system_info())

    # Check thresholds
    events = check_thresholds(all_metrics)

    # Send metrics
    if all_metrics:
        send_to_core("/api/v1/metrics", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "system",
            "agent_category": "system",
            "hostname": HOSTNAME,
            "metrics": all_metrics,
        })

    # Send error events
    if events:
        send_to_core("/api/v1/events", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "system",
            "agent_category": "system",
            "hostname": HOSTNAME,
            "events": events,
        })

    # Collect & send process list
    process_list = collect_process_list()
    if process_list:
        send_to_core("/api/v1/processes", {
            "agent_id": AGENT_ID,
            "processes": process_list,
        })

    # Collect & send system logs
    sys_logs = collect_system_logs()
    if sys_logs:
        send_to_core("/api/v1/logs", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "system",
            "agent_category": "system",
            "hostname": HOSTNAME,
            "logs": sys_logs,
        })

    # Heartbeat
    send_heartbeat()

    logger.info(f"Scan complete: {len(all_metrics)} metrics, {len(events)} events, {len(process_list)} processes, {len(sys_logs)} logs")


def run_daily_scan():
    """Full comprehensive scan for daily report."""
    logger.info("Running daily comprehensive scan...")
    run_scan()
    send_to_core("/api/v1/reports/generate", {"report_type": "daily", "channels": ["telegram"]})
    logger.info("Daily scan complete, report triggered")


def check_daily_schedule():
    now = datetime.now(timezone.utc)
    return now.hour == DAILY_SCAN_HOUR and now.minute == DAILY_SCAN_MINUTE


def main():
    os_display = {"linux": "Linux", "windows": "Windows", "darwin": "macOS"}.get(OS_TYPE, OS_TYPE)

    logger.info(f"=== Insight System Agent v{AGENT_VERSION} ===")
    logger.info(f"  Agent ID:      {AGENT_ID}")
    logger.info(f"  Agent Name:    {AGENT_NAME}")
    logger.info(f"  Hostname:      {HOSTNAME}")
    logger.info(f"  OS:            {os_display} ({platform.release()})")
    logger.info(f"  Core URL:      {CORE_API_URL}")
    logger.info(f"  Auth:          {'Token' if AGENT_TOKEN else 'API Key (legacy)'}")
    logger.info(f"  Scan Interval: {SCAN_INTERVAL}s")
    logger.info(f"  Thresholds:    CPU={CPU_THRESHOLD}%, RAM={MEMORY_THRESHOLD}%, Disk={DISK_THRESHOLD}%"))
    if OS_TYPE == "linux":
        logger.info(f"  Log files:     {LOG_FILES}")
        logger.info(f"  Journald:      {USE_JOURNALD}")
    elif OS_TYPE == "windows":
        logger.info(f"  WMI:           {'available' if wmi_available else 'not available (using PowerShell)'}")

    # Connect to core (token-based registration)
    connect_to_core()

    daily_done_today = False
    last_scan_day = None

    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()

            if last_scan_day != today:
                daily_done_today = False
                last_scan_day = today

            if check_daily_schedule() and not daily_done_today:
                run_daily_scan()
                daily_done_today = True
            else:
                run_scan()

        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
