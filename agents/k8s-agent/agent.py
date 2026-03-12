"""
Insight K8s Agent - Kubernetes Cluster Monitoring Agent

Features:
- Real-time pod monitoring (restarts, CrashLoopBackOff, error logs)
- Scheduled daily health scan (7:45 AM)
- Node resource usage monitoring (CPU, RAM, Disk)
- Sends data to Insight Core API
"""

import json
import logging
import os
import sys
import time
import threading
from datetime import datetime, timezone, timedelta

import requests

# ─── Configuration ───

CORE_API_URL = os.getenv("INSIGHT_CORE_URL", "http://localhost:8080")
API_KEY = os.getenv("INSIGHT_API_KEY", "insight-secret-key")
AGENT_ID = os.getenv("AGENT_ID", "k8s-agent-default")
AGENT_NAME = os.getenv("AGENT_NAME", "K8s Agent")
CLUSTER_NAME = os.getenv("CLUSTER_NAME", "default")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))  # seconds
DAILY_SCAN_HOUR = int(os.getenv("DAILY_SCAN_HOUR", "0"))  # UTC hour (7:45 AM UTC+7 = 0:45 UTC)
DAILY_SCAN_MINUTE = int(os.getenv("DAILY_SCAN_MINUTE", "45"))
LOG_TAIL_LINES = int(os.getenv("LOG_TAIL_LINES", "50"))
TARGET_NAMESPACES = os.getenv("TARGET_NAMESPACES", "all")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("insight.k8s-agent")

# K8s client
try:
    from kubernetes import client, config, watch
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster K8s config")
    except config.ConfigException:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")
    
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
except ImportError:
    logger.error("kubernetes package not installed. Install with: pip install kubernetes")
    sys.exit(1)
except Exception as e:
    logger.error(f"Failed to initialize K8s client: {e}")
    sys.exit(1)


# ─── Core API Communication ───


def send_to_core(endpoint: str, data: dict) -> bool:
    """Send data to Insight Core API."""
    url = f"{CORE_API_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }
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


def send_heartbeat():
    """Send heartbeat to core."""
    send_to_core(f"/api/v1/agents/{AGENT_ID}/heartbeat", {})


# ─── Cluster Summary ───


def collect_cluster_summary() -> list:
    """Collect cluster-level summary metrics (node/namespace/pod/service/event counts)."""
    metrics = []
    labels = {"cluster": CLUSTER_NAME}
    try:
        nodes = v1.list_node()
        metrics.append({"metric_name": "k8s_node_count", "metric_value": float(len(nodes.items)), "labels": labels})
    except Exception as e:
        logger.error(f"Failed to count nodes: {e}")
        metrics.append({"metric_name": "k8s_node_count", "metric_value": 0.0, "labels": labels})

    try:
        namespaces = v1.list_namespace()
        metrics.append({"metric_name": "k8s_namespace_count", "metric_value": float(len(namespaces.items)), "labels": labels})
    except Exception as e:
        logger.error(f"Failed to count namespaces: {e}")
        metrics.append({"metric_name": "k8s_namespace_count", "metric_value": 0.0, "labels": labels})

    try:
        pods = v1.list_pod_for_all_namespaces()
        metrics.append({"metric_name": "k8s_pod_count", "metric_value": float(len(pods.items)), "labels": labels})
    except Exception as e:
        logger.error(f"Failed to count pods: {e}")
        metrics.append({"metric_name": "k8s_pod_count", "metric_value": 0.0, "labels": labels})

    try:
        services = v1.list_service_for_all_namespaces()
        metrics.append({"metric_name": "k8s_service_count", "metric_value": float(len(services.items)), "labels": labels})
    except Exception as e:
        logger.error(f"Failed to count services: {e}")
        metrics.append({"metric_name": "k8s_service_count", "metric_value": 0.0, "labels": labels})

    try:
        warnings = v1.list_event_for_all_namespaces(field_selector="type=Warning")
        # Only count recent warnings (last 1h)
        recent = 0
        for ev in warnings.items:
            if ev.last_timestamp:
                event_time = ev.last_timestamp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - event_time <= timedelta(hours=1):
                    recent += 1
        metrics.append({"metric_name": "k8s_warning_event_count", "metric_value": float(recent), "labels": labels})
    except Exception as e:
        logger.error(f"Failed to count warning events: {e}")
        metrics.append({"metric_name": "k8s_warning_event_count", "metric_value": 0.0, "labels": labels})

    return metrics


# ─── Node Monitoring ───


def collect_node_metrics() -> list[dict]:
    """Collect CPU/RAM/conditions from all nodes."""
    metrics = []
    try:
        nodes = v1.list_node()
        for node in nodes.items:
            name = node.metadata.name
            status = node.status

            # Capacity
            capacity = status.capacity or {}
            allocatable = status.allocatable or {}

            cpu_capacity = _parse_cpu(capacity.get("cpu", "0"))
            mem_capacity = _parse_memory(capacity.get("memory", "0"))
            cpu_alloc = _parse_cpu(allocatable.get("cpu", "0"))
            mem_alloc = _parse_memory(allocatable.get("memory", "0"))

            labels = {"node": name, "cluster": CLUSTER_NAME}

            metrics.extend([
                {"metric_name": "node_cpu_capacity", "metric_value": cpu_capacity, "labels": labels},
                {"metric_name": "node_cpu_allocatable", "metric_value": cpu_alloc, "labels": labels},
                {"metric_name": "node_memory_capacity_bytes", "metric_value": mem_capacity, "labels": labels},
                {"metric_name": "node_memory_allocatable_bytes", "metric_value": mem_alloc, "labels": labels},
            ])

            # Conditions
            if status.conditions:
                for cond in status.conditions:
                    if cond.type == "Ready":
                        ready = 1.0 if cond.status == "True" else 0.0
                        metrics.append({
                            "metric_name": "node_ready",
                            "metric_value": ready,
                            "labels": labels,
                        })
                        if not ready:
                            logger.warning(f"Node {name} is NOT Ready!")

    except Exception as e:
        logger.error(f"Failed to collect node metrics: {e}")
    return metrics


def _parse_cpu(value: str) -> float:
    """Parse K8s CPU value to cores."""
    if value.endswith("m"):
        return float(value[:-1]) / 1000
    return float(value)


def _parse_memory(value: str) -> float:
    """Parse K8s memory value to bytes."""
    units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    return float(value)


# ─── Pod Monitoring ───


def collect_pod_metrics() -> tuple[list[dict], list[dict], list[dict]]:
    """
    Collect pod status and detect issues.
    Returns: (metrics, events, logs)
    """
    metrics = []
    events = []
    logs = []

    namespaces = _get_target_namespaces()

    for ns in namespaces:
        try:
            pods = v1.list_namespaced_pod(ns)
            
            running = 0
            pending = 0
            failed = 0
            total = len(pods.items)

            for pod in pods.items:
                pod_name = pod.metadata.name
                pod_labels = {"pod": pod_name, "namespace": ns, "cluster": CLUSTER_NAME}
                phase = pod.status.phase or "Unknown"

                if phase == "Running":
                    running += 1
                elif phase == "Pending":
                    pending += 1
                elif phase in ("Failed", "Unknown"):
                    failed += 1

                # Check container statuses for restarts and errors
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        restart_count = cs.restart_count or 0
                        
                        metrics.append({
                            "metric_name": "pod_restart_count",
                            "metric_value": float(restart_count),
                            "labels": {**pod_labels, "container": cs.name},
                        })

                        # Detect CrashLoopBackOff or Error
                        if cs.state:
                            if cs.state.waiting:
                                reason = cs.state.waiting.reason or ""
                                if reason in ("CrashLoopBackOff", "Error", "OOMKilled", "ImagePullBackOff"):
                                    events.append({
                                        "level": "error",
                                        "title": f"Pod {pod_name} - {reason}",
                                        "message": f"Container {cs.name} in pod {pod_name} ({ns}): {reason}. Restarts: {restart_count}",
                                        "source": f"k8s/{CLUSTER_NAME}",
                                        "namespace": ns,
                                        "resource": pod_name,
                                    })
                                    
                                    # Collect error logs
                                    pod_logs = _get_pod_logs(ns, pod_name, cs.name)
                                    if pod_logs:
                                        logs.append({
                                            "namespace": ns,
                                            "pod_name": pod_name,
                                            "container": cs.name,
                                            "log_level": "error",
                                            "message": pod_logs,
                                        })

                            elif cs.state.terminated:
                                reason = cs.state.terminated.reason or ""
                                exit_code = cs.state.terminated.exit_code
                                if exit_code != 0:
                                    events.append({
                                        "level": "error",
                                        "title": f"Pod {pod_name} terminated",
                                        "message": f"Container {cs.name} in {ns}: terminated with exit code {exit_code} ({reason})",
                                        "source": f"k8s/{CLUSTER_NAME}",
                                        "namespace": ns,
                                        "resource": pod_name,
                                    })

                        # High restart detection
                        if restart_count > 3:
                            events.append({
                                "level": "error" if restart_count > 5 else "warning",
                                "title": f"Pod {pod_name} high restarts",
                                "message": f"Container {cs.name} in {ns} has restarted {restart_count} times",
                                "source": f"k8s/{CLUSTER_NAME}",
                                "namespace": ns,
                                "resource": pod_name,
                            })

            # Namespace summary metrics
            ns_labels = {"namespace": ns, "cluster": CLUSTER_NAME}
            metrics.extend([
                {"metric_name": "pods_total", "metric_value": float(total), "labels": ns_labels},
                {"metric_name": "pods_running", "metric_value": float(running), "labels": ns_labels},
                {"metric_name": "pods_pending", "metric_value": float(pending), "labels": ns_labels},
                {"metric_name": "pods_failed", "metric_value": float(failed), "labels": ns_labels},
            ])

        except Exception as e:
            logger.error(f"Failed to collect pod metrics for {ns}: {e}")

    return metrics, events, logs


def _get_pod_logs(namespace: str, pod_name: str, container: str = None) -> str:
    """Get last N lines of pod logs."""
    try:
        kwargs = {
            "name": pod_name,
            "namespace": namespace,
            "tail_lines": LOG_TAIL_LINES,
            "previous": True,  # Get logs from previous crashed container
        }
        if container:
            kwargs["container"] = container
        return v1.read_namespaced_pod_log(**kwargs)
    except Exception:
        try:
            # Try without previous flag
            kwargs["previous"] = False
            return v1.read_namespaced_pod_log(**kwargs)
        except Exception as e:
            logger.debug(f"Could not get logs for {namespace}/{pod_name}: {e}")
            return ""


def _get_target_namespaces() -> list[str]:
    """Get list of namespaces to monitor."""
    if TARGET_NAMESPACES == "all":
        try:
            ns_list = v1.list_namespace()
            return [ns.metadata.name for ns in ns_list.items]
        except Exception:
            return ["default"]
    return [ns.strip() for ns in TARGET_NAMESPACES.split(",")]


# ─── K8s Events Monitoring ───


def collect_k8s_events() -> list[dict]:
    """Collect recent K8s warning events."""
    events = []
    try:
        k8s_events = v1.list_event_for_all_namespaces(
            field_selector="type=Warning",
        )
        for event in k8s_events.items:
            # Only report events from the last hour
            if event.last_timestamp:
                event_time = event.last_timestamp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - event_time > timedelta(hours=1):
                    continue

            events.append({
                "level": "warning",
                "title": f"K8s Event: {event.reason}",
                "message": f"[{event.involved_object.namespace}/{event.involved_object.name}] {event.message}",
                "source": f"k8s/{CLUSTER_NAME}",
                "namespace": event.involved_object.namespace or "",
                "resource": event.involved_object.name or "",
                "details": {
                    "reason": event.reason,
                    "type": event.type,
                    "count": event.count,
                    "kind": event.involved_object.kind,
                },
            })
    except Exception as e:
        logger.error(f"Failed to collect K8s events: {e}")
    return events


# ─── Main Loop ───


def run_scan():
    """Run a full scan and send results to core."""
    logger.info("Starting scan...")
    
    # Collect cluster summary
    cluster_summary = collect_cluster_summary()
    
    # Collect node metrics
    node_metrics = collect_node_metrics()
    
    # Collect pod metrics, events, and logs
    pod_metrics, pod_events, pod_logs = collect_pod_metrics()
    
    # Collect K8s events
    k8s_events = collect_k8s_events()

    all_metrics = cluster_summary + node_metrics + pod_metrics
    # Filter: only send error events, skip warnings for real-time alerts
    error_events = [e for e in pod_events if e.get("level") in ("error", "critical")]
    all_events = error_events + [e for e in k8s_events if e.get("level") in ("error", "critical")]

    # Send metrics
    if all_metrics:
        send_to_core("/api/v1/metrics", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "kubernetes",
            "agent_category": "kubernetes",
            "hostname": CLUSTER_NAME,
            "metrics": all_metrics,
        })

    # Send error events (these will trigger alerts in core)
    if all_events:
        send_to_core("/api/v1/events", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "kubernetes",
            "agent_category": "kubernetes",
            "hostname": CLUSTER_NAME,
            "events": all_events,
        })

    # Send error logs
    if pod_logs:
        send_to_core("/api/v1/logs", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "kubernetes",
            "agent_category": "kubernetes",
            "hostname": CLUSTER_NAME,
            "logs": pod_logs,
        })

    # Heartbeat
    send_heartbeat()

    logger.info(f"Scan complete: {len(all_metrics)} metrics, {len(all_events)} events, {len(pod_logs)} logs")


def run_daily_scan():
    """Full comprehensive scan for daily report."""
    logger.info("Running daily comprehensive scan...")
    
    # This is the same as regular scan but includes ALL events (not just errors)
    cluster_summary = collect_cluster_summary()
    node_metrics = collect_node_metrics()
    pod_metrics, pod_events, pod_logs = collect_pod_metrics()
    k8s_events = collect_k8s_events()

    all_metrics = cluster_summary + node_metrics + pod_metrics
    all_events = pod_events + k8s_events  # Include everything for daily report

    # Send all data
    if all_metrics:
        send_to_core("/api/v1/metrics", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "kubernetes",
            "agent_category": "kubernetes",
            "hostname": CLUSTER_NAME,
            "metrics": all_metrics,
        })

    if all_events:
        send_to_core("/api/v1/events", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "kubernetes",
            "agent_category": "kubernetes",
            "hostname": CLUSTER_NAME,
            "events": all_events,
        })

    if pod_logs:
        send_to_core("/api/v1/logs", {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "agent_type": "kubernetes",
            "agent_category": "kubernetes",
            "hostname": CLUSTER_NAME,
            "logs": pod_logs,
        })

    # Trigger report generation
    send_to_core("/api/v1/reports/generate", {
        "report_type": "daily",
        "channels": ["telegram"],
    })

    logger.info("Daily scan complete and report triggered")


def check_daily_schedule():
    """Check if it's time for the daily scan."""
    now = datetime.now(timezone.utc)
    return now.hour == DAILY_SCAN_HOUR and now.minute == DAILY_SCAN_MINUTE


def main():
    """Main agent loop."""
    logger.info(f"Insight K8s Agent starting...")
    logger.info(f"   Agent ID: {AGENT_ID}")
    logger.info(f"   Cluster: {CLUSTER_NAME}")
    logger.info(f"   Core URL: {CORE_API_URL}")
    logger.info(f"   Scan Interval: {SCAN_INTERVAL}s")
    logger.info(f"   Daily Scan: {DAILY_SCAN_HOUR:02d}:{DAILY_SCAN_MINUTE:02d} UTC")

    daily_done_today = False
    last_scan_day = None

    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()

            # Reset daily flag at start of new day
            if last_scan_day != today:
                daily_done_today = False
                last_scan_day = today

            # Check for daily scan
            if check_daily_schedule() and not daily_done_today:
                run_daily_scan()
                daily_done_today = True
            else:
                # Regular scan
                run_scan()

        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
